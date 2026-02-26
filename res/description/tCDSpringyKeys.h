#ifndef _tCDSpringyKeys_H_
#define _tCDSpringyKeys_H_

enum
{
	SPK_STRENGTH       = 1200,
	SPK_P_STIFFNESS    = 1201,
	SPK_P_DAMPING      = 1202,
	SPK_P_MASS         = 1203,
	SPK_USE_POSITION   = 1204,
	SPK_USE_ROTATION   = 1205,
	SPK_USE_SCALE      = 1206,
	SPK_SPLIT_FORCES   = 1300,
	SPK_POS_STATIC     = 1301,
	SPK_SCA_STATIC     = 1302,
	SPK_ROT_STATIC     = 1303,
	SPK_S_STIFFNESS    = 1304,
	SPK_S_DAMPING      = 1305,
	SPK_S_MASS         = 1306,
	SPK_R_STIFFNESS    = 1307,
	SPK_R_DAMPING      = 1308,
	SPK_R_MASS         = 1309,
	SPK_ID_FORCES      = 3000,
	SPK_ID_SPLIT       = 3001,
	SPK_ID_P           = 3002,
	SPK_ID_S           = 3003,
	SPK_ID_R           = 3004,
	// Internal state (tag storage)
	SPK_PREV_TIME      = 10000,
	SPK_PREV_M         = 10001,
	SPK_PREV_SCA       = 10002,
	SPK_PREV_FRAME     = 10003
};

#endif
