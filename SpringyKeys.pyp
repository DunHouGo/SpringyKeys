import math
import os
import c4d
from c4d import plugins

from dataclasses import dataclass, field
from typing import Any, Tuple

PLUGIN_ID_TAG = 1067631

SPK_PURCHASE = 1000
SPK_STRENGTH = 1200
SPK_P_STIFFNESS = 1201
SPK_P_DAMPING = 1202
SPK_P_MASS = 1203
SPK_USE_POSITION = 1204
SPK_USE_ROTATION = 1205
SPK_USE_SCALE = 1206
SPK_SPLIT_FORCES = 1300
SPK_POS_STATIC = 1301
SPK_SCA_STATIC = 1302
SPK_ROT_STATIC = 1303
SPK_S_STIFFNESS = 1304
SPK_S_DAMPING = 1305
SPK_S_MASS = 1306
SPK_R_STIFFNESS = 1307
SPK_R_DAMPING = 1308
SPK_R_MASS = 1309
SPK_ID_FORCES = 3000
SPK_ID_SPLIT = 3001
SPK_ID_P = 3002
SPK_ID_S = 3003
SPK_ID_R = 3004

SPK_PREV_TIME = 10000
SPK_PREV_M = 10001
SPK_PREV_SCA = 10002
SPK_PREV_FRAME = 10003

SPK_DEBUG = 11000

DEBUG_ENABLED = False

MAXFORCE = 1000000.0


def _clamp(x: float, mn: float, mx: float) -> float:
    if x < mn:
        return mn
    if x > mx:
        return mx
    return x


def _acos(x: float) -> float:
    return math.acos(_clamp(x, -1.0, 1.0))


def _sin(x: float) -> float:
    return math.sin(x)


def _cos(x: float) -> float:
    return math.cos(x)


def _vnorm(v: c4d.Vector) -> c4d.Vector:
    l = v.GetLength()
    if l <= 0.0:
        return c4d.Vector(0.0)
    return v / l


def _blend(a, b, mix: float):
    return a + (b - a) * mix


def _matrix_scale(m: c4d.Matrix) -> c4d.Vector:
    return c4d.Vector(m.v1.GetLength(), m.v2.GetLength(), m.v3.GetLength())


def _scale_matrix(m: c4d.Matrix, sca: c4d.Vector) -> c4d.Matrix:
    out = c4d.Matrix(m)
    out.v1 = _vnorm(out.v1) * sca.x
    out.v2 = _vnorm(out.v2) * sca.y
    out.v3 = _vnorm(out.v3) * sca.z
    return out


class _PyQuat:
    __slots__ = ("w", "x", "y", "z")

    def __init__(self, w: float = 1.0, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self.w = float(w)
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)

    @staticmethod
    def Identity() -> "_PyQuat":
        return _PyQuat(1.0, 0.0, 0.0, 0.0)

    def Copy(self) -> "_PyQuat":
        return _PyQuat(self.w, self.x, self.y, self.z)

    def Add(self, other: "_PyQuat") -> "_PyQuat":
        return _PyQuat(self.w + other.w, self.x + other.x, self.y + other.y, self.z + other.z)

    def Mul(self, other: "_PyQuat") -> "_PyQuat":
        aw, ax, ay, az = self.w, self.x, self.y, self.z
        bw, bx, by, bz = other.w, other.x, other.y, other.z
        return _PyQuat(
            aw * bw - ax * bx - ay * by - az * bz,
            ax * bw + aw * bx + ay * bz - az * by,
            ay * bw + aw * by + az * bx - ax * bz,
            az * bw + aw * bz + ax * by - ay * bx,
        )

    def MulScalar(self, s: float) -> "_PyQuat":
        return _PyQuat(self.w * s, self.x * s, self.y * s, self.z * s)

    def Conjugate(self) -> "_PyQuat":
        return _PyQuat(self.w, -self.x, -self.y, -self.z)

    def Length(self) -> float:
        return (self.w * self.w + self.x * self.x + self.y * self.y + self.z * self.z) ** 0.5

    def Normalized(self) -> "_PyQuat":
        l = self.Length()
        if l > 0.0:
            inv = 1.0 / l
            return _PyQuat(self.w * inv, self.x * inv, self.y * inv, self.z * inv)
        return _PyQuat.Identity()

    def Inverse(self) -> "_PyQuat":
        lsq = (self.w * self.w + self.x * self.x + self.y * self.y + self.z * self.z)
        if lsq > 0.0:
            qc = self.Conjugate()
            inv = 1.0 / lsq
            return _PyQuat(qc.w * inv, qc.x * inv, qc.y * inv, qc.z * inv)
        return _PyQuat.Identity()

    def AngleAxis(self) -> Tuple[float, c4d.Vector]:
        qn = self.Normalized()
        angle = 2.0 * _acos(qn.w)
        s = (1.0 - qn.w * qn.w) ** 0.5
        if s < 0.00001:
            axis = c4d.Vector(1.0, 0.0, 0.0)
        else:
            axis = c4d.Vector(qn.x / s, qn.y / s, qn.z / s)
        return angle, axis

    @staticmethod
    def Slerp(q1: "_PyQuat", q2: "_PyQuat", t: float) -> "_PyQuat":
        qa = q1.Normalized()
        qb = q2.Normalized()
        dot = qa.w * qb.w + qa.x * qb.x + qa.y * qb.y + qa.z * qb.z
        if dot < 0.0:
            qb = _PyQuat(-qb.w, -qb.x, -qb.y, -qb.z)
            dot = -dot

        if dot > 0.9995:
            res = _PyQuat(
                qa.w + t * (qb.w - qa.w),
                qa.x + t * (qb.x - qa.x),
                qa.y + t * (qb.y - qa.y),
                qa.z + t * (qb.z - qa.z),
            )
            return res.Normalized()

        theta0 = _acos(dot)
        sin_theta0 = math.sin(theta0)
        theta = theta0 * t
        sin_theta = math.sin(theta)

        s0 = math.cos(theta) - dot * sin_theta / sin_theta0
        s1 = sin_theta / sin_theta0
        return qa.MulScalar(s0).Add(qb.MulScalar(s1)).Normalized()

    @staticmethod
    def FromMatrix(m: c4d.Matrix) -> "_PyQuat":
        cq = c4d.Quaternion()
        cq.SetMatrix(m)
        return _PyQuat(float(cq.w), float(cq.v.x), float(cq.v.y), float(cq.v.z))

    def ToMatrix(self) -> c4d.Matrix:
        cq = c4d.Quaternion()
        cq.w = self.w
        cq.v = c4d.Vector(self.x, self.y, self.z)
        return cq.GetMatrix()


def _matrix_from_pyquat(q: _PyQuat) -> c4d.Matrix:
    return q.ToMatrix()


@dataclass(slots=True)
class _State:
    position: c4d.Vector = field(default_factory=lambda: c4d.Vector(0.0))
    momentum: c4d.Vector = field(default_factory=lambda: c4d.Vector(0.0))
    scale: c4d.Vector = field(default_factory=lambda: c4d.Vector(0.0))
    scaleMomentum: c4d.Vector = field(default_factory=lambda: c4d.Vector(0.0))
    orientation: _PyQuat = field(default_factory=_PyQuat.Identity)
    angularMomentum: c4d.Vector = field(default_factory=lambda: c4d.Vector(0.0))

    velocity: c4d.Vector = field(default_factory=lambda: c4d.Vector(0.0))
    scaleVelocity: c4d.Vector = field(default_factory=lambda: c4d.Vector(0.0))
    spin: _PyQuat = field(default_factory=lambda: _PyQuat(0.0, 0.0, 0.0, 0.0))
    angularVelocity: c4d.Vector = field(default_factory=lambda: c4d.Vector(0.0))

    pMass: float = 1.0
    invPMass: float = 1.0
    sMass: float = 1.0
    invSMass: float = 1.0
    rMass: float = 1.0
    invRMass: float = 1.0
    inertia: float = 0.01
    invInertia: float = 100.0

    targetOrientation: _PyQuat = field(default_factory=_PyQuat.Identity)

    def copy_from(self, src: "_State") -> None:
        self.position = c4d.Vector(src.position)
        self.momentum = c4d.Vector(src.momentum)
        self.velocity = c4d.Vector(src.velocity)

        self.scale = c4d.Vector(src.scale)
        self.scaleMomentum = c4d.Vector(src.scaleMomentum)
        self.scaleVelocity = c4d.Vector(src.scaleVelocity)

        self.orientation = src.orientation.Copy()
        self.spin = src.spin.Copy()

        self.angularMomentum = c4d.Vector(src.angularMomentum)
        self.angularVelocity = c4d.Vector(src.angularVelocity)

        self.pMass = float(src.pMass)
        self.invPMass = float(src.invPMass)
        self.sMass = float(src.sMass)
        self.invSMass = float(src.invSMass)
        self.rMass = float(src.rMass)
        self.invRMass = float(src.invRMass)
        self.inertia = float(src.inertia)
        self.invInertia = float(src.invInertia)

        self.targetOrientation = src.targetOrientation.Copy()

    def copy(self) -> "_State":
        s = _State()
        s.copy_from(self)
        return s


@dataclass(slots=True)
class _Deriv:
    velocity: c4d.Vector = field(default_factory=lambda: c4d.Vector(0.0))
    force: c4d.Vector = field(default_factory=lambda: c4d.Vector(0.0))
    spin: _PyQuat = field(default_factory=lambda: _PyQuat(0.0, 0.0, 0.0, 0.0))
    torque: c4d.Vector = field(default_factory=lambda: c4d.Vector(0.0))
    scaleVelocity: c4d.Vector = field(default_factory=lambda: c4d.Vector(0.0))
    scaleForce: c4d.Vector = field(default_factory=lambda: c4d.Vector(0.0))


def _copy_state(dst: "_State", src: "_State") -> None:
    dst.copy_from(src)


class _RungeKutta:
    def __init__(self):
        self.kP = self.bP = self.kS = self.bS = self.kR = self.bR = 1.0

    def set_spring_constants(self, kp, bp, ks, bs, kr, br, f):
        self.kP = kp * f
        self.bP = bp * kp * 0.08 * f
        self.kS = ks * f
        self.bS = bs * ks * 0.08 * f
        self.kR = kr * f
        self.bR = br * kr * 0.08 * f

    def recalc(self, s: _State):
        s.velocity = s.momentum * s.invPMass
        s.scaleVelocity = s.scaleMomentum * s.invSMass
        s.angularVelocity = s.angularMomentum * s.invInertia

        s.orientation = s.orientation.Normalized()

        av = s.angularVelocity
        wq = _PyQuat(0.0, av.x, av.y, av.z)
        s.spin = wq.Mul(s.orientation).MulScalar(0.5)

    def forces(self, s: _State):
        force = c4d.Vector(0.0)
        scaleForce = c4d.Vector(0.0)
        torque = c4d.Vector(0.0)

        if s.position.GetLength() > 0.0:
            force += (-self.kP * s.position.GetLength() * _vnorm(s.position) - self.bP * s.velocity)
        else:
            force += (-self.bP * s.velocity)

        if force.GetLength() > MAXFORCE:
            force = _vnorm(force) * MAXFORCE

        if s.scale.GetLength() > 0.0:
            scaleForce += (-self.kS * s.scale.GetLength() * _vnorm(s.scale) - self.bS * s.scaleVelocity)
        else:
            scaleForce += (-self.bS * s.scaleVelocity)

        if scaleForce.GetLength() > MAXFORCE:
            scaleForce = _vnorm(scaleForce) * MAXFORCE

        # 核心：旋转力计算
        # 目标：orientation -> targetOrientation
        # 旋转误差 diff = inverse(current) * target
        diff = s.orientation.Inverse().Mul(s.targetOrientation)
        angle, axis = diff.AngleAxis()
        
        # 原版 C++: torque += (kR * angle * _vnorm(axis)) - (bR * s.angularVelocity)
        if axis.GetLength() > 0.0:
            torque += (self.kR * angle * _vnorm(axis)) - (self.bR * s.angularVelocity)
        else:
            torque += -(self.bR * s.angularVelocity)

        return force, torque, scaleForce

    def _evaluate(self, s: _State) -> _Deriv:
        d = _Deriv()
        d.velocity = s.velocity
        d.scaleVelocity = s.scaleVelocity
        d.spin = s.spin
        d.force, d.torque, d.scaleForce = self.forces(s)
        return d

    def _evaluate_dt(self, s: _State, dt: float, d: _Deriv) -> _Deriv:
        ss = _State()
        ss.copy_from(s)

        ss.position = ss.position + d.velocity * dt
        ss.momentum = ss.momentum + d.force * dt
        ss.scale = ss.scale + d.scaleVelocity * dt
        ss.scaleMomentum = ss.scaleMomentum + d.scaleForce * dt
        ss.orientation = ss.orientation.Add(d.spin.MulScalar(dt))
        ss.angularMomentum = ss.angularMomentum + d.torque * dt

        self.recalc(ss)

        out = _Deriv()
        out.velocity = ss.velocity
        out.scaleVelocity = ss.scaleVelocity
        out.spin = ss.spin
        out.force, out.torque, out.scaleForce = self.forces(ss)
        return out

    def integrate(self, s: _State, dt: float):
        a = self._evaluate(s)
        b = self._evaluate_dt(s, dt * 0.5, a)
        c = self._evaluate_dt(s, dt * 0.5, b)
        d = self._evaluate_dt(s, dt, c)

        s.position = s.position + (dt / 6.0) * (a.velocity + 2.0 * (b.velocity + c.velocity) + d.velocity)
        s.momentum = s.momentum + (dt / 6.0) * (a.force + 2.0 * (b.force + c.force) + d.force)

        s.scale = s.scale + (dt / 6.0) * (a.scaleVelocity + 2.0 * (b.scaleVelocity + c.scaleVelocity) + d.scaleVelocity)
        s.scaleMomentum = s.scaleMomentum + (dt / 6.0) * (a.scaleForce + 2.0 * (b.scaleForce + c.scaleForce) + d.scaleForce)

        spin_sum = a.spin.Add(b.spin.Add(c.spin).MulScalar(2.0)).Add(d.spin)
        s.orientation = s.orientation.Add(spin_sum.MulScalar(dt / 6.0))
        s.angularMomentum = s.angularMomentum + (dt / 6.0) * (a.torque + 2.0 * (b.torque + c.torque) + d.torque)

        self.recalc(s)

    def interpolate(self, a: _State, b: _State, mix: float) -> _State:
        s = _State()
        s.position = _blend(a.position, b.position, mix)
        s.momentum = _blend(a.momentum, b.momentum, mix)
        s.scale = _blend(a.scale, b.scale, mix)
        s.scaleMomentum = _blend(a.scaleMomentum, b.scaleMomentum, mix)
        s.orientation = _PyQuat.Slerp(a.orientation, b.orientation, mix)
        s.angularMomentum = _blend(a.angularMomentum, b.angularMomentum, mix)

        s.pMass = a.pMass
        s.invPMass = a.invPMass
        s.sMass = a.sMass
        s.invSMass = a.invSMass
        s.rMass = a.rMass
        s.invRMass = a.invRMass
        s.inertia = a.inertia
        s.invInertia = a.invInertia

        self.recalc(s)
        return s


def _has_psr_animation(op: c4d.BaseObject) -> bool:
    if op is None:
        return False
    for did in (c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_POSITION, c4d.DTYPE_VECTOR, 0)),
                c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_SCALE, c4d.DTYPE_VECTOR, 0)),
                c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_ROTATION, c4d.DTYPE_VECTOR, 0))):
        tr = op.FindCTrack(did)
        if tr is not None:
            return True
    return False


def _first_keyframe(op: c4d.BaseObject, fps: int) -> int:
    frm = 2147483647
    for pid in (c4d.ID_BASEOBJECT_POSITION, c4d.ID_BASEOBJECT_SCALE, c4d.ID_BASEOBJECT_ROTATION):
        tr = op.FindCTrack(c4d.DescID(c4d.DescLevel(pid, c4d.DTYPE_VECTOR, 0)))
        if tr is None:
            continue
        crv = tr.GetCurve()
        if crv is None or crv.GetKeyCount() <= 0:
            continue
        t = crv.GetKey(0).GetTime()
        f = t.GetFrame(fps)
        if f < frm:
            frm = f
    return frm


def _last_keyframe(op: c4d.BaseObject, fps: int) -> int:
    frm = -2147483648
    for pid in (c4d.ID_BASEOBJECT_POSITION, c4d.ID_BASEOBJECT_SCALE, c4d.ID_BASEOBJECT_ROTATION):
        tr = op.FindCTrack(c4d.DescID(c4d.DescLevel(pid, c4d.DTYPE_VECTOR, 0)))
        if tr is None:
            continue
        crv = tr.GetCurve()
        if crv is None or crv.GetKeyCount() <= 0:
            continue
        kc = crv.GetKeyCount()
        t = crv.GetKey(kc - 1).GetTime()
        f = t.GetFrame(fps)
        if f > frm:
            frm = f
    return frm


def _frame_rate(doc: c4d.documents.BaseDocument) -> float:
    fps = float(doc.GetFps())
    btA = c4d.BaseTime(fps, fps)
    btB = c4d.BaseTime(fps - 1.0, fps)
    return btA.Get() - btB.Get()


class SpringyKeysTag(plugins.TagData):
    def __init__(self):
        super().__init__()
        self._t = 0.0
        self._rk4 = _RungeKutta()
        self._op_state = _State()
        self._prv_state = _State()

    def Init(self, node, isCloneInit=False):
        bc = node.GetDataInstance()
        if bc.GetInt32(SPK_DEBUG) != 0 and bc.GetInt32(SPK_DEBUG) != 1:
            bc.SetBool(SPK_DEBUG, False)
        bc.SetBool(SPK_USE_POSITION, True)
        bc.SetBool(SPK_USE_SCALE, False)
        bc.SetBool(SPK_USE_ROTATION, True)
        bc.SetFloat(SPK_STRENGTH, 1.0)
        bc.SetBool(SPK_SPLIT_FORCES, False)

        bc.SetFloat(SPK_P_STIFFNESS, 0.5)
        bc.SetFloat(SPK_P_DAMPING, 0.5)
        bc.SetFloat(SPK_P_MASS, 1.0)

        bc.SetFloat(SPK_S_STIFFNESS, 0.5)
        bc.SetFloat(SPK_S_DAMPING, 0.5)
        bc.SetFloat(SPK_S_MASS, 1.0)

        bc.SetFloat(SPK_R_STIFFNESS, 0.5)
        bc.SetFloat(SPK_R_DAMPING, 0.5)
        bc.SetFloat(SPK_R_MASS, 1.0)

        bc.SetFloat(SPK_PREV_TIME, 0.0)
        bc.SetMatrix(SPK_PREV_M, c4d.Matrix())
        bc.SetVector(SPK_PREV_SCA, c4d.Vector(1.0, 1.0, 1.0))
        bc.SetInt32(SPK_PREV_FRAME, 0)

        self._t = 0.0
        self._op_state = _State()
        self._prv_state = _State()

        # 初始状态设为单位矩阵/归一化状态
        self._op_state.position = c4d.Vector(0, 0, 0)
        self._op_state.momentum = c4d.Vector(0, 0, 0)
        self._op_state.velocity = c4d.Vector(0, 0, 0)
        self._op_state.scale = c4d.Vector(0, 0, 0)
        self._op_state.scaleMomentum = c4d.Vector(0, 0, 0)
        self._op_state.scaleVelocity = c4d.Vector(0, 0, 0)
        self._op_state.orientation = _PyQuat.Identity()
        self._op_state.spin = _PyQuat(0.0, 0.0, 0.0, 0.0)
        self._op_state.angularMomentum = c4d.Vector(0, 0, 0)
        self._op_state.angularVelocity = c4d.Vector(0, 0, 0)
        self._op_state.targetOrientation = _PyQuat.Identity()

        # 记录初始 PSR 防止添加时跳转
        op = node.GetObject()
        if op:
            bc.SetMatrix(SPK_PREV_M, op.GetMl())
            bc.SetVector(SPK_PREV_SCA, op.GetAbsScale())
            doc = op.GetDocument()
            if doc:
                bc.SetFloat(SPK_PREV_TIME, doc.GetTime().Get())
                bc.SetInt32(SPK_PREV_FRAME, doc.GetTime().GetFrame(doc.GetFps()))

        # 设置优先级不依赖相机
        priority = node[c4d.EXPRESSION_PRIORITY]
        if priority:
            priority.SetPriorityValue(c4d.PRIORITYVALUE_CAMERADEPENDENT, False)
            node[c4d.EXPRESSION_PRIORITY] = priority

        return True

    def GetDDescription(self, node, description, flags):
        if not description.LoadDescription("tCDSpringyKeys"):
            return False

        bc = node.GetDataInstance()
        split = bc.GetBool(SPK_SPLIT_FORCES)

        # 处理 P 组 (Position Forces)
        db_p = description.GetParameterI(c4d.DescID(SPK_ID_P), None)
        if db_p:
            if not split:
                db_p[c4d.DESC_NAME] = "" # 移除分组标题使其看起来像直接在 Forces 下
            else:
                db_p[c4d.DESC_NAME] = "Position Forces"
            db_p[c4d.DESC_HIDE] = False

        # 处理 S 组 (Scale Forces)
        db_s = description.GetParameterI(c4d.DescID(SPK_ID_S), None)
        if db_s:
            db_s[c4d.DESC_HIDE] = not split

        # 处理 R 组 (Rotation Forces)
        db_r = description.GetParameterI(c4d.DescID(SPK_ID_R), None)
        if db_r:
            db_r[c4d.DESC_HIDE] = not split

        return (True, flags | c4d.DESCFLAGS_DESC_LOADED)

    def CopyTo(self, dest, snode, dnode, flags, trn):
        try:
            dest._op_state = self._op_state
            dest._prv_state = self._prv_state
            dest._t = self._t
        except Exception:
            pass
        return True

    def GetDEnabling(self, node, id, t_data, flags, itemdesc):
        tag = node
        op = tag.GetObject() if tag else None
        if op is None:
            return False
        if not _has_psr_animation(op):
            return False
        return True

    def Execute(self, tag, doc, op, bt, priority, flags):
        bc = tag.GetDataInstance()

        dbg = DEBUG_ENABLED or bc.GetBool(SPK_DEBUG)
        if dbg:
            try:
                print("[SpringyKeys] Execute", doc.GetTime().Get(), "frm", doc.GetTime().GetFrame(doc.GetFps()), "flags", flags)
            except Exception:
                pass
        
        trgM = op.GetMl()
        opSca = op.GetAbsScale()
        bTime = doc.GetTime()
        curTime = bTime.Get()
        fps = doc.GetFps()
        curFrm = bTime.GetFrame(fps)

        if not _has_psr_animation(op):
            # 即使没有动画，也要实时更新历史记录，防止后续添加 Tag 或 K 帧时使用旧的（通常是单位矩阵）记录导致跳变
            bc.SetMatrix(SPK_PREV_M, trgM)
            bc.SetVector(SPK_PREV_SCA, opSca)
            bc.SetFloat(SPK_PREV_TIME, curTime)
            bc.SetInt32(SPK_PREV_FRAME, curFrm)
            return c4d.EXECUTIONRESULT_OK

        # 设置弹簧常数
        kp = bc.GetFloat(SPK_P_STIFFNESS)
        bp = bc.GetFloat(SPK_P_DAMPING)
        
        f = 1500.0
        if not bc.GetBool(SPK_SPLIT_FORCES):
            bc.SetFloat(SPK_S_STIFFNESS, kp)
            bc.SetFloat(SPK_S_DAMPING, bp)
            bc.SetFloat(SPK_S_MASS, bc.GetFloat(SPK_P_MASS))
            
            bc.SetFloat(SPK_R_STIFFNESS, kp)
            bc.SetFloat(SPK_R_DAMPING, bp)
            bc.SetFloat(SPK_R_MASS, bc.GetFloat(SPK_P_MASS))
            
            ks, bs, kr, br = kp, bp, kp, bp
        else:
            ks = bc.GetFloat(SPK_S_STIFFNESS)
            bs = bc.GetFloat(SPK_S_DAMPING)
            kr = bc.GetFloat(SPK_R_STIFFNESS)
            br = bc.GetFloat(SPK_R_DAMPING)
            
        self._rk4.set_spring_constants(kp, bp, ks, bs, kr, br, f)

        trgM = op.GetMl()
        opSca = op.GetAbsScale()

        bTime = doc.GetTime()
        curTime = bTime.Get()
        prvTime = bc.GetFloat(SPK_PREV_TIME)

        fps = doc.GetFps()
        curFrm = bTime.GetFrame(fps)
        prvFrm = bc.GetInt32(SPK_PREV_FRAME)

        # 初始启动检测
        initStart = False
        firstFrm = _first_keyframe(op, fps)
        lastFrm = _last_keyframe(op, fps)

        # 如果没有动画轨道，_has_psr_animation 已经处理并更新了记录
        # 如果有轨道但没有关键帧，这里确保不发生跳变
        if firstFrm == 2147483647:
            bc.SetMatrix(SPK_PREV_M, trgM)
            bc.SetVector(SPK_PREV_SCA, opSca)
            bc.SetFloat(SPK_PREV_TIME, curTime)
            bc.SetInt32(SPK_PREV_FRAME, curFrm)
            return c4d.EXECUTIONRESULT_OK

        if c4d.CheckIsRunning(c4d.CHECKISRUNNING_ANIMATIONRUNNING):
            # 12412: Go to Start, 12411: Go to End
            if c4d.IsCommandChecked(12412) and curFrm <= firstFrm:
                initStart = True
            if c4d.IsCommandChecked(12411) and lastFrm != -2147483648 and curFrm >= lastFrm:
                initStart = True
        elif curFrm <= firstFrm:
            initStart = True

        if initStart:
            self._op_state = _State()
            bc.SetFloat(SPK_PREV_TIME, curTime)
            bc.SetMatrix(SPK_PREV_M, trgM)
            bc.SetVector(SPK_PREV_SCA, opSca)
            bc.SetInt32(SPK_PREV_FRAME, curFrm)
            return c4d.EXECUTIONRESULT_OK

        # 处理 curTime == prvTime 的重置逻辑
        if curTime == prvTime:
            resetPSR = False
            if c4d.CheckIsRunning(c4d.CHECKISRUNNING_ANIMATIONRUNNING):
                resetPSR = True
            else:
                if op.GetBit(c4d.BIT_ACTIVE):
                    keyState = c4d.BaseContainer()
                    c4d.gui.GetInputState(c4d.BFM_INPUT_KEYBOARD, c4d.BFM_INPUT_CHANNEL, keyState)
                    if keyState.GetInt32(c4d.BFM_INPUT_QUALIFIER) & c4d.QALT:
                        resetPSR = True
                    else:
                        # 对应 C++ 版的 flags & CD_EXECUTION_ANIMATION / IN_DRAG
                        if (flags & c4d.EXECUTIONFLAGS_ANIMATION) or (flags & c4d.EXECUTIONFLAGS_INDRAG):
                            resetPSR = True
                else:
                    resetPSR = True

            if resetPSR:
                op.SetMl(bc.GetMatrix(SPK_PREV_M))
                op.SetAbsScale(bc.GetVector(SPK_PREV_SCA))
            return c4d.EXECUTIONRESULT_OK

        strength = bc.GetFloat(SPK_STRENGTH)
        if strength == 0.0:
            return c4d.EXECUTIONRESULT_OK

        # 核心逻辑：deltaTime 处理与积分
        # 原版使用 ScaleMatrix 构建 prM，在 Python 中手动构建
        prM = _scale_matrix(c4d.Matrix(), opSca)
        prM.off = trgM.off

        prvM = bc.GetMatrix(SPK_PREV_M)
        locM = ~trgM * prvM
        locM.off = (~prM) * prvM.off

        trgSca = opSca
        prvSca = bc.GetVector(SPK_PREV_SCA)
        scaM = _scale_matrix(c4d.Matrix(), trgSca) # 使用 trgSca 构建
        scaM.off = trgSca
        locSca = (~scaM) * prvSca

        # 构建当前状态
        curState = _State()
        _copy_state(curState, self._op_state)
        
        curState.position = locM.off
        curState.pMass = max(1.0, bc.GetFloat(SPK_P_MASS))
        curState.invPMass = 1.0 / curState.pMass

        curState.scale = locSca
        curState.sMass = max(1.0, bc.GetFloat(SPK_S_MASS))
        curState.invSMass = 1.0 / curState.sMass

        curState.orientation = _PyQuat.FromMatrix(locM)
        curState.targetOrientation = _PyQuat.Identity()
        curState.rMass = max(1.0, bc.GetFloat(SPK_R_MASS))
        curState.invRMass = 1.0 / curState.rMass
        curState.inertia = 4.0 * curState.rMass * (1.0 / 6.0)
        if curState.inertia < 0.01:
            curState.inertia = 0.01
        curState.invInertia = 1.0 / curState.inertia

        fRate = _frame_rate(doc)
        deltaTime = abs(curTime - prvTime)

        if deltaTime > fRate * 2.0:
            frmDif = abs(curFrm - prvFrm) if prvFrm != curFrm else 1
            dt = 0.01
            tCounter = 0.0
            tPrv = self._t
            while tCounter < (fRate * frmDif):
                self._rk4.integrate(curState, dt)
                self._t += dt
                tCounter += dt
            
            self._prv_state = _State()
            self._prv_state.copy_from(curState)
            self._rk4.integrate(curState, dt)

            mix = fRate / tCounter if tCounter > 0 else 1.0
            self._op_state = self._rk4.interpolate(self._prv_state, curState, mix)
            self._t = _blend(tPrv, self._t, mix)
        else:
            self._rk4.integrate(curState, deltaTime)
            self._op_state = curState

        if dbg:
            try:
                print("[SpringyKeys] locRotQ", curState.orientation.w, curState.orientation.x, curState.orientation.y, curState.orientation.z)
                print("[SpringyKeys] angVel", self._op_state.angularVelocity, "angMom", self._op_state.angularMomentum)
            except Exception:
                pass

        # 设置物体位姿
        # 原版 C++:
        # Matrix dtRotM = opState.orientation.GetMatrix();
        # dtRotM.off = opState.position;
        # opQ.SetMatrix(trgM * dtRotM);
        # trgQ.SetMatrix(trgM);

        # 弹簧状态转换回局部矩阵
        dtRotM = self._op_state.orientation.ToMatrix() #_matrix_from_pyquat(self._op_state.orientation)
        dtRotM.off = self._op_state.position

        # 计算弹簧影响下的目标世界矩阵（不含缩放）
        # trgM 是动画矩阵，dtRotM 是相对于 trgM 的偏移
        finalM = trgM * dtRotM
        
        opQ = _PyQuat.FromMatrix(finalM)
        trgQ = _PyQuat.FromMatrix(trgM)

        # 对旋转进行混合 (Strength)
        if not bc.GetBool(SPK_USE_ROTATION):
            mixQ = trgQ
        else:
            mixQ = _PyQuat.Slerp(trgQ, opQ, strength)
        
        # 得到混合后的最终变换矩阵 (初始包含混合后的旋转)
        transM = mixQ.ToMatrix() #_matrix_from_pyquat(mixQ)

        # 设置位置 (Position)
        # 原版 C++: Vector opPos = prM * opState.position;
        opPos = prM * self._op_state.position
        
        if not bc.GetBool(SPK_USE_POSITION):
            transM.off = trgM.off
        else:
            transM.off = _blend(trgM.off, opPos, strength)

        # 设置缩放
        dtSca = scaM * self._op_state.scale
        if not bc.GetBool(SPK_USE_SCALE):
            tranSca = trgSca
        else:
            tranSca = _blend(trgSca, dtSca, strength)

        # 应用变换
        # 只设置矩阵与缩放；不要写回 AbsRot，否则会覆盖/干扰动画曲线表现
        op.SetMl(transM)
        op.SetAbsScale(tranSca)

        bc.SetFloat(SPK_PREV_TIME, curTime)
        bc.SetMatrix(SPK_PREV_M, transM)
        bc.SetVector(SPK_PREV_SCA, tranSca)
        bc.SetInt32(SPK_PREV_FRAME, curFrm)

        return c4d.EXECUTIONRESULT_OK



if __name__ == '__main__':
    bmp = c4d.bitmaps.BaseBitmap()
    plugin_path, _ = os.path.split(__file__)
    bmp.InitWith(os.path.join(plugin_path, "res", "icons", "icon.png"))
    plugins.RegisterTagPlugin(
        id=PLUGIN_ID_TAG,
        str="Springy Keys",
        info=c4d.TAG_EXPRESSION | c4d.TAG_VISIBLE,
        g=SpringyKeysTag,
        description="tCDSpringyKeys",
        icon=bmp,
    )
