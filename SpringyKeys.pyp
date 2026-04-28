import copy
import json
import math
import os
import c4d
from c4d import plugins
from c4d.plugins import GeLoadString

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Cinema 4D Python API baseline: https://developers.maxon.net/docs/py/2025_3_1/index.html

PLUGIN_ID_TAG = 1068107
# Optional menu commands (Extensions / search Command Manager). Register in PluginCafé if needed.
PLUGIN_ID_CMD_BAKE_ALL = 1068108
PLUGIN_ID_CMD_UNBAKE_ALL = 1068109
# Must match basename of res/description/<name>.res (RegisterTagPlugin / LoadDescription).
PLUGIN_DESC_NAME = "tcdspringykeys_cache"

IDS_CDSPRNGKYS = 10000
IDS_STIFFNESS = 10001
IDS_DAMPING = 10002
IDS_MASS = 10003
IDS_POS_FORCES = 10004
IDS_SCA_FORCES = 10005
IDS_ROT_FORCES = 10006
IDS_POSITION_FORCES = 10007
IDS_TAG_NAME = 10008
IDS_CMD_BAKE_ALL = 10009
IDS_CMD_UNBAKE_ALL = 10010
IDS_STATUS_BAKE_SAMPLING = 10011
IDS_STATUS_BAKE_WRITING = 10012
IDS_MSG_DESC_LOAD_FAILED = 10013
IDS_MSG_BAKE_ALL_NONE = 10014
IDS_MSG_BAKE_ALL_DONE = 10015
IDS_MSG_BAKE_ALL_SKIPPED = 10016
IDS_MSG_UNBAKE_ALL_NONE = 10017
IDS_MSG_UNBAKE_ALL_DONE = 10018
IDS_MSG_UNBAKE_ALL_NOTE = 10019
IDS_MSG_BAKE_NEED_HOST = 10020
IDS_MSG_BAKE_ALREADY_LOCKED = 10021
IDS_MSG_BAKE_FAILED = 10022
IDS_MSG_BAKE_DONE = 10023
IDS_MSG_BAKE_FRAME_RANGE = 10024
IDS_MSG_BAKE_LOCK_NOTICE = 10025
IDS_MSG_UNBAKE_NO_BACKUP = 10026
IDS_MSG_UNBAKE_FAILED = 10027
IDS_MSG_UNBAKE_DONE = 10028
IDS_MSG_REGISTER_TAG_FAILED = 10029
IDS_MSG_REGISTER_CMD_FAILED = 10030

_LOAD_DESC_FAIL_LOGGED = False

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
SPK_ID_BAKE = 4000
SPK_BAKE_PSR = 4010
SPK_RESTORE_PSR = 4011
# Stored on tag: after Bake Keys, spring forces are disabled until Un-Bake Keys.
SPK_FORCES_LOCKED_BY_BAKE = 4012
# Serialized pre-bake key snapshot (hidden STRING in description; survives save / reopen).
SPK_PSR_BACKUP_PAYLOAD = 4013
# True once SPK_PREV_* has been synced from the host object (avoids SetMl(identity) on add).
SPK_RUNTIME_SEEDED = 4014
# Scene-wide actions (same logic as menu commands).
SPK_BAKE_ALL_IN_SCENE = 4016
SPK_UNBAKE_ALL_IN_SCENE = 4017
# Last Rel PSR sampled while timeline is not playing; unkeyed axes read from here during playback.
SPK_CACHE_REL_POS = 4018
SPK_CACHE_REL_ROT = 4019
SPK_CACHE_REL_SCA = 4020
# True once SPK_CACHE_REL_* was written from the object (Init / editor-time refresh).
SPK_REL_CACHE_VALID = 4021

SPK_PREV_TIME = 10000
SPK_PREV_M = 10001
SPK_PREV_SCA = 10002
SPK_PREV_FRAME = 10003

SPK_DEBUG = 11000

DEBUG_ENABLED = False

# Parameters greyed out while SPK_FORCES_LOCKED_BY_BAKE (Execute skips spring).
_SPK_FORCE_PARAM_IDS = frozenset(
    {
        SPK_USE_POSITION,
        SPK_USE_ROTATION,
        SPK_USE_SCALE,
        SPK_STRENGTH,
        SPK_ID_FORCES,
        SPK_SPLIT_FORCES,
        SPK_ID_SPLIT,
        SPK_ID_P,
        SPK_ID_S,
        SPK_ID_R,
        SPK_P_STIFFNESS,
        SPK_P_DAMPING,
        SPK_P_MASS,
        SPK_S_STIFFNESS,
        SPK_S_DAMPING,
        SPK_S_MASS,
        SPK_R_STIFFNESS,
        SPK_R_DAMPING,
        SPK_R_MASS,
    }
)

MAXFORCE = 1000000.0


def _show_message_dialog(message: str) -> None:
    """Show a user-facing message dialog when the plugin needs explicit feedback."""
    try:
        c4d.gui.MessageDialog(message)
    except Exception:
        pass


def _show_status_text(message: str) -> None:
    """Show a non-blocking status message in the Cinema 4D status bar."""
    try:
        c4d.gui.StatusSetText(message)
    except Exception:
        pass


def _load_string(symbol_id: int, default: str) -> str:
    """Load a localized string from the plugin resource and fall back to ``default``."""
    try:
        value: str = GeLoadString(symbol_id)
        if value:
            return value
    except Exception:
        pass
    return default


def _format_string(symbol_id: int, default: str, **kwargs: object) -> str:
    """Load and format a localized string template."""
    template: str = _load_string(symbol_id, default)
    try:
        return template.format(**kwargs)
    except Exception:
        return template


def _show_bake_all_result(baked_count: int, skipped_locked_count: int) -> None:
    """Report the Bake All result to the user."""
    if baked_count == 0 and skipped_locked_count == 0:
        _show_status_text(
            _load_string(
                IDS_MSG_BAKE_ALL_NONE,
                "Bake All: no Springy Keys tags were found in this document.",
            )
        )
        return

    message: str = _format_string(
        IDS_MSG_BAKE_ALL_DONE,
        "Bake All completed on {count} tag(s).",
        count=baked_count,
    )
    if skipped_locked_count:
        message += "\n" + _format_string(
            IDS_MSG_BAKE_ALL_SKIPPED,
            "Skipped {count} baked tag(s). Please un-bake them first.",
            count=skipped_locked_count,
        )
    _show_status_text(message)


def _show_unbake_all_result(invoked_count: int) -> None:
    """Report the Un-Bake All result to the user."""
    if invoked_count == 0:
        _show_status_text(
            _load_string(
                IDS_MSG_UNBAKE_ALL_NONE,
                "Un-Bake All: no Springy Keys tags were found in this document.",
            )
        )
        return

    _show_status_text(
        _format_string(
            IDS_MSG_UNBAKE_ALL_DONE,
            "Un-Bake All completed on {count} tag(s).",
            count=invoked_count,
        )
        + "\n"
        + _load_string(
            IDS_MSG_UNBAKE_ALL_NOTE,
            "Only tags with a saved bake backup were restored.",
        )
    )


def _psr_backup_to_json(backup: Optional[Dict[str, Any]]) -> str:
    if not backup:
        return ""
    return json.dumps(backup, separators=(",", ":"))


def _psr_backup_from_json(s: str) -> Optional[Dict[str, Any]]:
    if not s or not str(s).strip():
        return None
    try:
        out = json.loads(s)
        if isinstance(out, dict) and "channels" in out:
            return out
    except Exception:
        pass
    return None


def _vec_comp_desc(base_vec: int, comp: int) -> c4d.DescID:
    return c4d.DescID(
        c4d.DescLevel(base_vec, c4d.DTYPE_VECTOR, 0),
        c4d.DescLevel(comp, c4d.DTYPE_REAL, 0),
    )


def _component_curve_value(
    op: c4d.BaseObject, base_vec: int, comp: int, doc: c4d.documents.BaseDocument
) -> Optional[float]:
    tr = op.FindCTrack(_vec_comp_desc(base_vec, comp))
    if tr is None:
        return None
    cr = tr.GetCurve()
    if cr is None or cr.GetKeyCount() < 1:
        return None
    fps = max(int(doc.GetFps()), 1)
    t = doc.GetTime()
    try:
        return float(cr.GetValue(t, fps))
    except Exception:
        try:
            return float(cr.GetValue(t))
        except Exception:
            return None


def _merge_vector_from_keys_and_cache(
    op: c4d.BaseObject,
    doc: c4d.documents.BaseDocument,
    base_vec: int,
    cached: c4d.Vector,
) -> c4d.Vector:
    out = c4d.Vector(cached)
    vx = _component_curve_value(op, base_vec, c4d.VECTOR_X, doc)
    vy = _component_curve_value(op, base_vec, c4d.VECTOR_Y, doc)
    vz = _component_curve_value(op, base_vec, c4d.VECTOR_Z, doc)
    if vx is not None:
        out.x = vx
    if vy is not None:
        out.y = vy
    if vz is not None:
        out.z = vz
    return out


def _spring_animated_target_ml(op: c4d.BaseObject, doc: c4d.documents.BaseDocument, bc: c4d.BaseContainer) -> c4d.Matrix:
    """Spring drive target: each keyed P/S/R component from its curve; others from cached editor Rel PSR."""
    anim_running = c4d.CheckIsRunning(c4d.CHECKISRUNNING_ANIMATIONRUNNING)
    if not anim_running:
        bc.SetVector(SPK_CACHE_REL_POS, op.GetRelPos())
        bc.SetVector(SPK_CACHE_REL_ROT, op.GetRelRot())
        bc.SetVector(SPK_CACHE_REL_SCA, op.GetRelScale())
        bc.SetBool(SPK_REL_CACHE_VALID, True)

    if anim_running and not bc.GetBool(SPK_REL_CACHE_VALID, False):
        # Older scenes / tags before cache ids: fall back to evaluated matrix until editor pause refreshes cache.
        return op.GetMl()

    cp = bc.GetVector(SPK_CACHE_REL_POS, c4d.Vector(0))
    cr = bc.GetVector(SPK_CACHE_REL_ROT, c4d.Vector(0))
    cs = bc.GetVector(SPK_CACHE_REL_SCA, c4d.Vector(1.0, 1.0, 1.0))

    p = _merge_vector_from_keys_and_cache(op, doc, c4d.ID_BASEOBJECT_POSITION, cp)
    r = _merge_vector_from_keys_and_cache(op, doc, c4d.ID_BASEOBJECT_ROTATION, cr)
    s = _merge_vector_from_keys_and_cache(op, doc, c4d.ID_BASEOBJECT_SCALE, cs)

    m = c4d.utils.HPBToMatrix(r)
    m.off = p
    m.v1 *= s.x
    m.v2 *= s.y
    m.v3 *= s.z
    return m


def _snapshot_component_curve(op: c4d.BaseObject, base_vec: int, comp: int) -> List[dict]:
    tr = op.FindCTrack(_vec_comp_desc(base_vec, comp))
    if tr is None:
        return []
    cr = tr.GetCurve()
    if cr is None:
        return []
    out: List[dict] = []
    for i in range(cr.GetKeyCount()):
        k = cr.GetKey(i)
        t = k.GetTime()
        try:
            interp = int(k.GetInterpolation(cr))
        except Exception:
            interp = int(c4d.CINTERPOLATION_SPLINE)
        try:
            v = float(k.GetValue())
        except Exception:
            v = 0.0
        out.append(
            {
                "n": int(t.GetNumerator()),
                "d": int(t.GetDenominator()),
                "v": v,
                "i": interp,
            }
        )
    return out


def _snapshot_psr_keys(op: c4d.BaseObject) -> Dict[str, Any]:
    backup: Dict[str, Any] = {
        "channels": {
            "pos": {},
            "rot": {},
            "sca": {},
        }
    }
    for ch_name, base in (
        ("pos", c4d.ID_BASEOBJECT_POSITION),
        ("rot", c4d.ID_BASEOBJECT_ROTATION),
        ("sca", c4d.ID_BASEOBJECT_SCALE),
    ):
        for comp, comp_id in zip("xyz", (c4d.VECTOR_X, c4d.VECTOR_Y, c4d.VECTOR_Z)):
            backup["channels"][ch_name][comp] = _snapshot_component_curve(op, base, comp_id)
    return backup


def _restore_component_curve(
    op: c4d.BaseObject, doc: c4d.documents.BaseDocument, base_vec: int, comp: int, keys_data: List[dict]
) -> None:
    did = _vec_comp_desc(base_vec, comp)
    tr = op.FindCTrack(did)
    if tr is None:
        if not keys_data:
            return
        tr = c4d.CTrack(op, did)
        op.InsertTrackSorted(tr)
    cr = tr.GetCurve()
    if cr is None:
        return
    cr.FlushKeys()
    for kd in keys_data:
        t = c4d.BaseTime(int(kd["n"]), int(kd["d"]))
        kd_res = cr.AddKey(t)
        if kd_res is None:
            continue
        key = kd_res["key"]
        idx = int(kd_res["nidx"])
        key.SetValue(cr, float(kd["v"]))
        cr.SetKeyDefault(doc, idx)
        try:
            key.SetInterpolation(cr, int(kd["i"]))
        except Exception:
            pass


def _restore_psr_keys_from_backup(op: c4d.BaseObject, doc: c4d.documents.BaseDocument, backup: Dict[str, Any]) -> None:
    ch = backup.get("channels") or {}
    mapping = (
        ("pos", c4d.ID_BASEOBJECT_POSITION),
        ("rot", c4d.ID_BASEOBJECT_ROTATION),
        ("sca", c4d.ID_BASEOBJECT_SCALE),
    )
    for ch_name, base in mapping:
        comp_data = ch.get(ch_name) or {}
        for comp, comp_id in zip("xyz", (c4d.VECTOR_X, c4d.VECTOR_Y, c4d.VECTOR_Z)):
            lst = comp_data.get(comp) or []
            _restore_component_curve(op, doc, base, comp_id, lst)


def _delete_keys_in_frame_range_on_curve(
    op: c4d.BaseObject, base_vec: int, comp: int, fps: int, f0: int, f1: int
) -> None:
    tr = op.FindCTrack(_vec_comp_desc(base_vec, comp))
    if tr is None:
        return
    cr = tr.GetCurve()
    if cr is None:
        return
    to_del: List[int] = []
    for i in range(cr.GetKeyCount()):
        k = cr.GetKey(i)
        fr = int(k.GetTime().GetFrame(fps))
        if f0 <= fr <= f1:
            to_del.append(i)
    for i in reversed(to_del):
        cr.DelKey(i)


def _add_real_keyframe(
    op: c4d.BaseObject,
    doc: c4d.documents.BaseDocument,
    base_vec: int,
    comp: int,
    btime: c4d.BaseTime,
    value: float,
    interpolation: int = c4d.CINTERPOLATION_SPLINE,
) -> None:
    did = _vec_comp_desc(base_vec, comp)
    tr = op.FindCTrack(did)
    if tr is None:
        tr = c4d.CTrack(op, did)
        op.InsertTrackSorted(tr)
    cr = tr.GetCurve()
    if cr is None:
        return
    kd_res = cr.AddKey(btime)
    if kd_res is None:
        return
    key = kd_res["key"]
    idx = int(kd_res["nidx"])
    key.SetValue(cr, float(value))
    cr.SetKeyDefault(doc, idx)
    try:
        key.SetInterpolation(cr, int(interpolation))
    except Exception:
        pass


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


def _vector_psr_desc_ids():
    """Legacy whole-vector tracks (some scenes key P/S/R as one vector track)."""
    return (
        c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_POSITION, c4d.DTYPE_VECTOR, 0)),
        c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_SCALE, c4d.DTYPE_VECTOR, 0)),
        c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_ROTATION, c4d.DTYPE_VECTOR, 0)),
    )


def _iter_psr_component_tracks(op: c4d.BaseObject):
    for base in (c4d.ID_BASEOBJECT_POSITION, c4d.ID_BASEOBJECT_SCALE, c4d.ID_BASEOBJECT_ROTATION):
        for comp in (c4d.VECTOR_X, c4d.VECTOR_Y, c4d.VECTOR_Z):
            tr = op.FindCTrack(_vec_comp_desc(base, comp))
            if tr is not None:
                yield tr


def _has_psr_animation(op: c4d.BaseObject) -> bool:
    if op is None:
        return False
    for tr in _iter_psr_component_tracks(op):
        cr = tr.GetCurve()
        if cr is not None and cr.GetKeyCount() > 0:
            return True
    for did in _vector_psr_desc_ids():
        tr = op.FindCTrack(did)
        if tr is not None:
            cr = tr.GetCurve()
            if cr is not None and cr.GetKeyCount() > 0:
                return True
    return False


def _first_keyframe(op: c4d.BaseObject, fps: int) -> int:
    frm = 2147483647
    for tr in _iter_psr_component_tracks(op):
        crv = tr.GetCurve()
        if crv is None or crv.GetKeyCount() <= 0:
            continue
        t = crv.GetKey(0).GetTime()
        f = t.GetFrame(fps)
        if f < frm:
            frm = f
    for did in _vector_psr_desc_ids():
        tr = op.FindCTrack(did)
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
    for tr in _iter_psr_component_tracks(op):
        crv = tr.GetCurve()
        if crv is None or crv.GetKeyCount() <= 0:
            continue
        kc = crv.GetKeyCount()
        t = crv.GetKey(kc - 1).GetTime()
        f = t.GetFrame(fps)
        if f > frm:
            frm = f
    for did in _vector_psr_desc_ids():
        tr = op.FindCTrack(did)
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


def _scene_preview_frame_range(doc: c4d.documents.BaseDocument) -> Tuple[int, int]:
    """Timeline / preview range (GetMinTime … GetMaxTime), integer frames."""
    fps = max(int(doc.GetFps()), 1)
    sf = int(doc.GetMinTime().GetFrame(fps))
    ef = int(doc.GetMaxTime().GetFrame(fps))
    if ef < sf:
        sf, ef = ef, sf
    return sf, ef


def _walk_object_hierarchy(first: Optional[c4d.BaseObject]):
    op = first
    while op:
        yield op
        down = op.GetDown()
        if down:
            yield from _walk_object_hierarchy(down)
        op = op.GetNext()


def _iter_springy_tags(doc: c4d.documents.BaseDocument):
    if doc is None:
        return
    for obj in _walk_object_hierarchy(doc.GetFirstObject()):
        tag = obj.GetFirstTag()
        while tag:
            if tag.GetType() == PLUGIN_ID_TAG:
                yield tag
            tag = tag.GetNext()


def _invoke_springy_tag_button(tag: c4d.BaseTag, button_id: int) -> None:
    """Trigger the same code path as clicking a BUTTON in the tag AM."""
    did = c4d.DescID(c4d.DescLevel(button_id, c4d.DTYPE_BUTTON, 0))
    tag.Message(c4d.MSG_DESCRIPTION_COMMAND, {"id": did, "descid": did})


def springy_keys_run_bake_all_on_document(doc: c4d.documents.BaseDocument) -> Tuple[int, int]:
    """Bake every Springy Keys tag in ``doc``. Returns ``(baked_count, skipped_locked_count)``."""
    tags = list(_iter_springy_tags(doc))
    n = 0
    skipped = 0
    for tag in tags:
        bc = tag.GetDataInstance()
        if bc and bc.GetBool(SPK_FORCES_LOCKED_BY_BAKE):
            skipped += 1
            continue
        _invoke_springy_tag_button(tag, SPK_BAKE_PSR)
        n += 1
    c4d.EventAdd()
    return n, skipped


def springy_keys_run_unbake_all_on_document(doc: c4d.documents.BaseDocument) -> int:
    """Un-bake every Springy Keys tag in ``doc``. Returns how many tags were invoked."""
    tags = list(_iter_springy_tags(doc))
    for tag in tags:
        _invoke_springy_tag_button(tag, SPK_RESTORE_PSR)
    c4d.EventAdd()
    return len(tags)


def _desc_command_first_id(data) -> Optional[int]:
    if data is None:
        return None
    try:
        did = data["id"]
        return did[0].id
    except Exception:
        pass
    try:
        did = data["descid"]
        return did[0].id
    except Exception:
        pass
    return None


class SpringyKeysTag(plugins.TagData):
    def __init__(self):
        super().__init__()
        self._t = 0.0
        self._rk4 = _RungeKutta()
        self._op_state = _State()
        self._prv_state = _State()
        self._psr_key_backup: Optional[Dict[str, Any]] = None

    def Init(self, node, isCloneInit=False):
        bc = node.GetDataInstance()
        if bc is None:
            return False

        if not isCloneInit:
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

        self._t = 0.0
        self._op_state = _State()
        self._prv_state = _State()

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

        # Sync stored pose from the host. Never leave SPK_PREV_M as identity while the object
        # has a transform — Init can run before GetObject() is valid; Execute seeds later if needed.
        op = node.GetObject()
        if op:
            bc.SetMatrix(SPK_PREV_M, op.GetMl())
            bc.SetVector(SPK_PREV_SCA, op.GetAbsScale())
            doc = op.GetDocument()
            if doc:
                bc.SetFloat(SPK_PREV_TIME, doc.GetTime().Get())
                bc.SetInt32(SPK_PREV_FRAME, doc.GetTime().GetFrame(doc.GetFps()))
            bc.SetVector(SPK_CACHE_REL_POS, op.GetRelPos())
            bc.SetVector(SPK_CACHE_REL_ROT, op.GetRelRot())
            bc.SetVector(SPK_CACHE_REL_SCA, op.GetRelScale())
            bc.SetBool(SPK_REL_CACHE_VALID, True)
            bc.SetBool(SPK_RUNTIME_SEEDED, True)
        else:
            bc.SetMatrix(SPK_PREV_M, c4d.Matrix())
            bc.SetVector(SPK_PREV_SCA, c4d.Vector(1.0, 1.0, 1.0))
            bc.SetFloat(SPK_PREV_TIME, 0.0)
            bc.SetInt32(SPK_PREV_FRAME, 0)
            bc.SetBool(SPK_RUNTIME_SEEDED, False)

        pd = node[c4d.EXPRESSION_PRIORITY]
        if pd is None:
            pd = c4d.PriorityData()
        if pd is not None:
            pd.SetPriorityValue(c4d.PRIORITYVALUE_CAMERADEPENDENT, False)
            node[c4d.EXPRESSION_PRIORITY] = pd

        return True

    def GetDDescription(self, node, description, flags):
        global _LOAD_DESC_FAIL_LOGGED
        if not description.LoadDescription(PLUGIN_DESC_NAME):
            if not _LOAD_DESC_FAIL_LOGGED:
                _LOAD_DESC_FAIL_LOGGED = True
            return False

        bc = node.GetDataInstance()
        if bc is not None:
            try:
                split = bc.GetBool(SPK_SPLIT_FORCES)
                db_p = description.GetParameterI(c4d.DescID(SPK_ID_P), None)
                if db_p:
                    if not split:
                        db_p[c4d.DESC_NAME] = ""
                    else:
                        db_p[c4d.DESC_NAME] = _load_string(IDS_POSITION_FORCES, "Position Forces")
                    db_p[c4d.DESC_HIDE] = False
                db_s = description.GetParameterI(c4d.DescID(SPK_ID_S), None)
                if db_s:
                    db_s[c4d.DESC_HIDE] = not split
                db_r = description.GetParameterI(c4d.DescID(SPK_ID_R), None)
                if db_r:
                    db_r[c4d.DESC_HIDE] = not split
                db_payload = description.GetParameterI(
                    c4d.DescID(c4d.DescLevel(SPK_PSR_BACKUP_PAYLOAD, c4d.DTYPE_STRING, 0)), None
                )
                if db_payload:
                    db_payload[c4d.DESC_HIDE] = True
            except Exception:
                pass

        return (True, flags | c4d.DESCFLAGS_DESC_LOADED)

    def Message(self, node, type, data):
        if type == c4d.MSG_DESCRIPTION_COMMAND:
            cid = _desc_command_first_id(data)
            if cid == SPK_BAKE_PSR:
                self._bake_psr(node)
                return True
            if cid == SPK_RESTORE_PSR:
                self._restore_psr_from_backup(node)
                return True
            if cid == SPK_BAKE_ALL_IN_SCENE:
                doc = node.GetDocument()
                if doc is not None:
                    n, skipped = springy_keys_run_bake_all_on_document(doc)
                    _show_bake_all_result(n, skipped)
                return True
            if cid == SPK_UNBAKE_ALL_IN_SCENE:
                doc = node.GetDocument()
                if doc is not None:
                    k = springy_keys_run_unbake_all_on_document(doc)
                    _show_unbake_all_result(k)
                return True
        # Python TagData has no super.Message; returning True is correct for unhandled messages.
        return True

    def CopyTo(self, dest, snode, dnode, flags, trn):
        # Do not share _State instances with the source tag — that caused duplicated objects to
        # snap or fight the original when playback updated one tag's integrator for both.
        try:
            dest._op_state = _State()
            dest._prv_state = _State()
            dest._t = 0.0
            dest._psr_key_backup = copy.deepcopy(self._psr_key_backup) if self._psr_key_backup else None
        except Exception:
            dest._op_state = _State()
            dest._prv_state = _State()
            dest._t = 0.0
        try:
            tag = dnode
            if tag is not None and isinstance(tag, c4d.BaseTag):
                op = tag.GetObject()
                bc = tag.GetDataInstance()
                doc = tag.GetDocument()
                if op is not None and bc is not None:
                    bc.SetMatrix(SPK_PREV_M, op.GetMl())
                    bc.SetVector(SPK_PREV_SCA, op.GetAbsScale())
                    if doc is not None:
                        bc.SetFloat(SPK_PREV_TIME, doc.GetTime().Get())
                        bc.SetInt32(SPK_PREV_FRAME, doc.GetTime().GetFrame(max(int(doc.GetFps()), 1)))
                    bc.SetVector(SPK_CACHE_REL_POS, op.GetRelPos())
                    bc.SetVector(SPK_CACHE_REL_ROT, op.GetRelRot())
                    bc.SetVector(SPK_CACHE_REL_SCA, op.GetRelScale())
                    bc.SetBool(SPK_REL_CACHE_VALID, True)
                    bc.SetBool(SPK_RUNTIME_SEEDED, True)
        except Exception:
            pass
        return True

    def _psr_backup_resolve(self, tag: c4d.BaseTag) -> Optional[Dict[str, Any]]:
        if self._psr_key_backup is not None:
            return self._psr_key_backup
        bc = tag.GetDataInstance()
        if bc is None:
            return None
        return _psr_backup_from_json(bc.GetString(SPK_PSR_BACKUP_PAYLOAD, ""))

    def GetDEnabling(self, node, id, t_data, flags, itemdesc):
        try:
            pid = id[0].id
        except Exception:
            return True
        bc = node.GetDataInstance()
        locked = bool(bc.GetBool(SPK_FORCES_LOCKED_BY_BAKE)) if bc else False
        if pid == SPK_RESTORE_PSR:
            return self._psr_backup_resolve(node) is not None
        if pid == SPK_BAKE_PSR:
            return not locked
        if locked and pid in _SPK_FORCE_PARAM_IDS:
            return False
        return True

    def _bake_psr(self, node):
        tag = node
        doc = tag.GetDocument() if tag else None
        op = tag.GetObject() if tag else None
        if doc is None or op is None:
            _show_status_text(
                _load_string(
                    IDS_MSG_BAKE_NEED_HOST,
                    "Bake Keys requires a valid host object and document.",
                )
            )
            return
        bc = tag.GetDataInstance()
        if bc is None:
            return
        if bc.GetBool(SPK_FORCES_LOCKED_BY_BAKE):
            _show_status_text(
                _load_string(
                    IDS_MSG_BAKE_ALREADY_LOCKED,
                    "This tag is already baked. Please run Un-Bake Keys before baking again.",
                )
            )
            return
        fps = max(int(doc.GetFps()), 1)
        sf, ef = _scene_preview_frame_range(doc)
        if ef < sf:
            sf, ef = ef, sf
        span = ef - sf + 1
        if span <= 0:
            return
        if span > 300000:
            ef = sf + 300000 - 1

        saved = doc.GetTime()
        doc.StartUndo()
        bake_ok = False
        try:
            doc.AddUndo(c4d.UNDO_CHANGE, op)
            doc.AddUndo(c4d.UNDO_CHANGE, tag)
            self._psr_key_backup = _snapshot_psr_keys(op)
            # Sample while original keys still exist. Deleting keys in the bake range first
            # removes the animation that drives the spring, so ExecutePasses sees a static pose
            # (often zeros) and baked keys are wrong.
            samples: List[Tuple[c4d.Vector, c4d.Vector, c4d.Vector]] = []
            c4d.gui.StatusSetSpin()
            c4d.gui.StatusSetText(
                _load_string(
                    IDS_STATUS_BAKE_SAMPLING,
                    "Springy Keys: sampling for Bake Keys...",
                )
            )
            for f in range(sf, ef + 1):
                doc.SetTime(c4d.BaseTime(f, fps))
                doc.ExecutePasses(None, True, True, True, 0)
                samples.append((op.GetRelPos(), op.GetRelRot(), op.GetRelScale()))

            for base in (c4d.ID_BASEOBJECT_POSITION, c4d.ID_BASEOBJECT_ROTATION, c4d.ID_BASEOBJECT_SCALE):
                for comp in (c4d.VECTOR_X, c4d.VECTOR_Y, c4d.VECTOR_Z):
                    _delete_keys_in_frame_range_on_curve(op, base, comp, fps, sf, ef)

            c4d.gui.StatusSetText(
                _load_string(
                    IDS_STATUS_BAKE_WRITING,
                    "Springy Keys: writing keys...",
                )
            )
            bake_interp = c4d.CINTERPOLATION_LINEAR
            for i, f in enumerate(range(sf, ef + 1)):
                bt = c4d.BaseTime(f, fps)
                p, r, s = samples[i]
                _add_real_keyframe(
                    op, doc, c4d.ID_BASEOBJECT_POSITION, c4d.VECTOR_X, bt, p.x, bake_interp
                )
                _add_real_keyframe(
                    op, doc, c4d.ID_BASEOBJECT_POSITION, c4d.VECTOR_Y, bt, p.y, bake_interp
                )
                _add_real_keyframe(
                    op, doc, c4d.ID_BASEOBJECT_POSITION, c4d.VECTOR_Z, bt, p.z, bake_interp
                )
                _add_real_keyframe(
                    op, doc, c4d.ID_BASEOBJECT_ROTATION, c4d.VECTOR_X, bt, r.x, bake_interp
                )
                _add_real_keyframe(
                    op, doc, c4d.ID_BASEOBJECT_ROTATION, c4d.VECTOR_Y, bt, r.y, bake_interp
                )
                _add_real_keyframe(
                    op, doc, c4d.ID_BASEOBJECT_ROTATION, c4d.VECTOR_Z, bt, r.z, bake_interp
                )
                _add_real_keyframe(op, doc, c4d.ID_BASEOBJECT_SCALE, c4d.VECTOR_X, bt, s.x, bake_interp)
                _add_real_keyframe(op, doc, c4d.ID_BASEOBJECT_SCALE, c4d.VECTOR_Y, bt, s.y, bake_interp)
                _add_real_keyframe(op, doc, c4d.ID_BASEOBJECT_SCALE, c4d.VECTOR_Z, bt, s.z, bake_interp)
            bc.SetBool(SPK_FORCES_LOCKED_BY_BAKE, True)
            bc.SetString(SPK_PSR_BACKUP_PAYLOAD, _psr_backup_to_json(self._psr_key_backup))
            bake_ok = True
        except Exception as ex:
            _show_message_dialog(
                _format_string(
                    IDS_MSG_BAKE_FAILED,
                    "Bake Keys failed.\n{error}",
                    error=ex,
                )
            )
        finally:
            try:
                doc.SetTime(saved)
            except Exception:
                pass
            c4d.gui.StatusClear()
            doc.EndUndo()
        c4d.EventAdd()
        if bake_ok:
            try:
                tag.SetDirty(c4d.DIRTYFLAGS_DATA)
            except Exception:
                pass
            _show_status_text(
                _format_string(
                    IDS_MSG_BAKE_DONE,
                    "Bake Keys completed for '{name}'.",
                    name=op.GetName(),
                )
                + "\n"
                + _format_string(
                    IDS_MSG_BAKE_FRAME_RANGE,
                    "Frame range: {start}-{end}",
                    start=sf,
                    end=ef,
                )
                + "\n"
                + _load_string(
                    IDS_MSG_BAKE_LOCK_NOTICE,
                    "Spring forces are now locked until Un-Bake Keys is used.",
                )
            )

    def _restore_psr_from_backup(self, node):
        tag = node
        doc = tag.GetDocument() if tag else None
        op = tag.GetObject() if tag else None
        if doc is None or op is None:
            return
        backup = self._psr_backup_resolve(tag)
        if backup is None:
            _show_status_text(
                _load_string(
                    IDS_MSG_UNBAKE_NO_BACKUP,
                    "No baked backup was found. Please run Bake Keys first.",
                )
            )
            return
        bc = tag.GetDataInstance()
        doc.StartUndo()
        try:
            doc.AddUndo(c4d.UNDO_CHANGE, op)
            doc.AddUndo(c4d.UNDO_CHANGE, tag)
            _restore_psr_keys_from_backup(op, doc, backup)
            if bc is not None:
                bc.SetBool(SPK_FORCES_LOCKED_BY_BAKE, False)
                bc.SetString(SPK_PSR_BACKUP_PAYLOAD, "")
                bc.SetMatrix(SPK_PREV_M, op.GetMl())
                bc.SetVector(SPK_PREV_SCA, op.GetAbsScale())
                bc.SetFloat(SPK_PREV_TIME, doc.GetTime().Get())
                bc.SetInt32(SPK_PREV_FRAME, doc.GetTime().GetFrame(max(int(doc.GetFps()), 1)))
                bc.SetBool(SPK_RUNTIME_SEEDED, True)
            self._psr_key_backup = None
            self._t = 0.0
            self._op_state = _State()
            self._prv_state = _State()
        except Exception as ex:
            _show_message_dialog(
                _format_string(
                    IDS_MSG_UNBAKE_FAILED,
                    "Un-Bake Keys failed.\n{error}",
                    error=ex,
                )
            )
        finally:
            doc.EndUndo()
        c4d.EventAdd()
        try:
            tag.SetDirty(c4d.DIRTYFLAGS_DATA)
        except Exception:
            pass
        _show_status_text(
            _load_string(
                IDS_MSG_UNBAKE_DONE,
                "Un-Bake Keys completed. The pre-bake keys were restored and spring forces were re-enabled.",
            )
        )

    def Execute(self, tag, doc, op, bt, priority, flags):
        bc = tag.GetDataInstance()
        if bc is None:
            return c4d.EXECUTIONRESULT_OK
        if bc.GetBool(SPK_FORCES_LOCKED_BY_BAKE):
            return c4d.EXECUTIONRESULT_OK

        trgM = op.GetMl()
        opSca = op.GetAbsScale()
        bTime = doc.GetTime()
        curTime = bTime.Get()
        fps = doc.GetFps()
        curFrm = bTime.GetFrame(fps)

        if not _has_psr_animation(op):
            # 即使没有动画，也要实时更新历史记录，防止后续添加 Tag 或 K 帧时使用旧的（通常是单位矩阵）记录导致跳变
            bc.SetVector(SPK_CACHE_REL_POS, op.GetRelPos())
            bc.SetVector(SPK_CACHE_REL_ROT, op.GetRelRot())
            bc.SetVector(SPK_CACHE_REL_SCA, op.GetRelScale())
            bc.SetBool(SPK_REL_CACHE_VALID, True)
            bc.SetMatrix(SPK_PREV_M, trgM)
            bc.SetVector(SPK_PREV_SCA, opSca)
            bc.SetFloat(SPK_PREV_TIME, curTime)
            bc.SetInt32(SPK_PREV_FRAME, curFrm)
            bc.SetBool(SPK_RUNTIME_SEEDED, True)
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

        trgM = _spring_animated_target_ml(op, doc, bc)
        opSca = op.GetAbsScale()

        bTime = doc.GetTime()
        curTime = bTime.Get()
        prvTime = bc.GetFloat(SPK_PREV_TIME)

        fps = doc.GetFps()
        curFrm = bTime.GetFrame(fps)
        prvFrm = bc.GetInt32(SPK_PREV_FRAME)

        if not bc.GetBool(SPK_RUNTIME_SEEDED, False):
            bc.SetMatrix(SPK_PREV_M, trgM)
            bc.SetVector(SPK_PREV_SCA, opSca)
            bc.SetFloat(SPK_PREV_TIME, curTime)
            bc.SetInt32(SPK_PREV_FRAME, curFrm)
            bc.SetBool(SPK_RUNTIME_SEEDED, True)
            self._op_state = _State()
            self._prv_state = _State()
            self._t = 0.0
            return c4d.EXECUTIONRESULT_OK

        if curFrm == 0 and prvFrm != 0:
            self._op_state = _State()
            self._prv_state = _State()
            self._t = 0.0
            bc.SetFloat(SPK_PREV_TIME, curTime)
            bc.SetMatrix(SPK_PREV_M, trgM)
            bc.SetVector(SPK_PREV_SCA, opSca)
            bc.SetInt32(SPK_PREV_FRAME, curFrm)
            return c4d.EXECUTIONRESULT_OK

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
        elif curFrm <= firstFrm and (prvFrm > firstFrm or prvFrm < curFrm):
            # Do not fire on every motion-blur sub-sample at the same integer frame (curFrm==prvFrm).
            initStart = True

        if initStart:
            self._op_state = _State()
            bc.SetFloat(SPK_PREV_TIME, curTime)
            bc.SetMatrix(SPK_PREV_M, trgM)
            bc.SetVector(SPK_PREV_SCA, opSca)
            bc.SetInt32(SPK_PREV_FRAME, curFrm)
            return c4d.EXECUTIONRESULT_OK

        # Same doc time as SPK_PREV_TIME (multipass / motion blur). Match original CD_SpringyKeys:
        # when the object is selected (BIT_ACTIVE) and time is not advancing, only snap back to
        # the last spring pose if animation is running, Alt is held, or Cinema passes animation /
        # drag execution flags — otherwise the user can move the object in the editor.
        if curTime == prvTime:
            reset_psr = False
            if c4d.CheckIsRunning(c4d.CHECKISRUNNING_ANIMATIONRUNNING):
                reset_psr = True
            else:
                if op.GetBit(c4d.BIT_ACTIVE):
                    keybc = c4d.BaseContainer()
                    if c4d.gui.GetInputState(c4d.BFM_INPUT_KEYBOARD, c4d.BFM_INPUT_CHANNEL, keybc):
                        if keybc.GetInt32(c4d.BFM_INPUT_QUALIFIER) & c4d.QALT:
                            reset_psr = True
                    if int(flags) & int(c4d.EXECUTIONFLAGS_ANIMATION):
                        reset_psr = True
                    if int(flags) & int(c4d.EXECUTIONFLAGS_INDRAG):
                        reset_psr = True
                else:
                    reset_psr = True
            prvM = bc.GetMatrix(SPK_PREV_M)
            curM = op.GetMl()
            prvSca = bc.GetVector(SPK_PREV_SCA)
            curSca = op.GetAbsScale()
            # If the object was moved in the editor (e.g. unkeyed axis) while time did not advance,
            # SPK_PREV_* can stay stale; on play reset_psr becomes True and would SetMl that stale
            # matrix — snapping back. Only replay from cache when it still matches the object.
            pos_mismatch = (prvM.off - curM.off).GetLengthSquared() > 1e-10
            sca_mismatch = (prvSca - curSca).GetLengthSquared() > 1e-10
            v1 = prvM.v1.GetNormalized()
            v2 = prvM.v2.GetNormalized()
            v3 = prvM.v3.GetNormalized()
            w1 = curM.v1.GetNormalized()
            w2 = curM.v2.GetNormalized()
            w3 = curM.v3.GetNormalized()
            rot_mismatch = (
                (v1 - w1).GetLengthSquared() > 1e-10
                or (v2 - w2).GetLengthSquared() > 1e-10
                or (v3 - w3).GetLengthSquared() > 1e-10
            )
            mismatch = pos_mismatch or sca_mismatch or rot_mismatch
            if reset_psr and not mismatch:
                op.SetMl(prvM)
                op.SetAbsScale(prvSca)
            elif mismatch:
                bc.SetMatrix(SPK_PREV_M, curM)
                bc.SetVector(SPK_PREV_SCA, curSca)
                self._op_state = _State()
                self._prv_state = _State()
                self._t = 0.0
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

        # Match C++ tag: SetMl then choose continuous Euler with GetOptimalAngle, then abs scale.
        old_rot = op.GetAbsRot()
        op.SetMl(transM)
        new_rot = op.GetAbsRot()
        try:
            rot_set = c4d.utils.GetOptimalAngle(old_rot, new_rot, op.GetRotationOrder())
        except Exception:
            rot_set = new_rot
        op.SetAbsRot(rot_set)
        op.SetAbsScale(tranSca)

        bc.SetFloat(SPK_PREV_TIME, curTime)
        bc.SetMatrix(SPK_PREV_M, transM)
        bc.SetVector(SPK_PREV_SCA, tranSca)
        bc.SetInt32(SPK_PREV_FRAME, curFrm)

        return c4d.EXECUTIONRESULT_OK


class SpringyKeysBakeAllCommand(plugins.CommandData):
    """Menu command: same as tag button Bake All."""

    def Execute(self, doc):
        if doc is None:
            doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return False
        n, skipped = springy_keys_run_bake_all_on_document(doc)
        _show_bake_all_result(n, skipped)
        return True


class SpringyKeysUnbakeAllCommand(plugins.CommandData):
    """Menu command: same as tag button Un-Bake All."""

    def Execute(self, doc):
        if doc is None:
            doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return False
        k = springy_keys_run_unbake_all_on_document(doc)
        _show_unbake_all_result(k)
        return True


if __name__ == '__main__':
    plugin_path, _ = os.path.split(__file__)
    icon_path = os.path.join(plugin_path, "res", "icons", "icon.png")
    tag_icon = None
    if os.path.isfile(icon_path):
        bmp = c4d.bitmaps.BaseBitmap()
        if bmp.InitWith(icon_path)[0] == c4d.IMAGERESULT_OK:
            tag_icon = bmp
    reg_ok = plugins.RegisterTagPlugin(
        id=PLUGIN_ID_TAG,
        str=_load_string(IDS_TAG_NAME, "Springy Keys (Bake PSR)"),
        info=c4d.TAG_EXPRESSION | c4d.TAG_VISIBLE,
        g=SpringyKeysTag,
        description=PLUGIN_DESC_NAME,
        icon=tag_icon,
    )

    for cmd_id, title, cls in (
        (
            PLUGIN_ID_CMD_BAKE_ALL,
            _load_string(IDS_CMD_BAKE_ALL, "Springy Keys: Bake All"),
            SpringyKeysBakeAllCommand,
        ),
        (
            PLUGIN_ID_CMD_UNBAKE_ALL,
            _load_string(IDS_CMD_UNBAKE_ALL, "Springy Keys: Un-Bake All"),
            SpringyKeysUnbakeAllCommand,
        ),
    ):
        reg_cmd_ok: bool = plugins.RegisterCommandPlugin(
            id=cmd_id,
            str=title,
            info=0,
            help="",
            icon=None,
            dat=cls(),
        )
