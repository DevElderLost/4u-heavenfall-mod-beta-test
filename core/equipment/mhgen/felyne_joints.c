/* A Felyne takes its body piece's skeleton (core/equipment/mhgen/felyne_pack.py, patch_joints).
 *
 * MH4U poses a Felyne with the joints of its actor, the base Felyne's skeleton: a body piece is skinned with the
 * actor's joint matrices (its flag +0xc4b, FUN_0095a3a8) and a helm's joints copy them (uMHchar::Constraint,
 * FUN_00b05070). The game moves the actor's joints for its own bodies built on joints of their own, and only for
 * those: the lobby copies the body's joints 4, 7, 10 and 12 (FUN_00697b00), a quest and a cutscene write two bodies'
 * values by their id (FUN_00699d5c, FUN_0069a484). MH XX has no base skeleton: a Felyne's actor is its body piece,
 * so every joint is the body's. felyne_body_joints does that for every joint of the actor but the root, which the
 * motions place: the body's rest translation, or the actor's own model's for a joint the body lacks.
 *
 * Changes: FUN_00697b00 (the lobby, after a cat's body loads: the lobby's, the Smithy's preview, the Gathering Hall's
 * cats, the hunter select screen) is felyne_lobby_joints. FUN_00699d5c (a quest cat's piece, at its setup and every
 * frame; felyne_joints.s) first calls felyne_quest_joints. FUN_001a0ab8 (a cat in a cutscene; felyne_joints.s) calls
 * felyne_body_joints before its body's FUN_006997c4 and FUN_0069a484. The game's own writes by id come after and give
 * the same values as the bodies' files.
 *
 * A model (uModel): +0x220 its joint count, +0x224 its joints (JOINT_SIZE each), +0x228 the table joint number ->
 * joint (NO_JOINT: none), +0xf0 its resource (rModel), whose +0x64 are the bone records (BONE_SIZE each, in the joints'
 * order; +0x0c the place under the parent). A joint: +0x48 its rest translation (x, y, z, w 0; the motions' translation
 * of a joint they do not move, FUN_0095be38), +0x97 its number.
 */
typedef unsigned int u32;
typedef unsigned char u8;

#define MODEL_JOINT_COUNT 0x220
#define MODEL_JOINTS 0x224
#define MODEL_JOINT_TABLE 0x228
#define MODEL_RESOURCE 0xF0
#define RESOURCE_BONES 0x64
#define JOINT_SIZE 0xA8
#define JOINT_REST 0x48
#define JOINT_NUMBER 0x97
#define BONE_SIZE 0x18
#define BONE_PLACE 0x0C
#define NO_JOINT 0xFF
#define ROOT_JOINT 0
#define LOBBY_STATUS 0xE2C          /* a lobby cat: its status; +0x160 its pieces, whose +0xe8 is the body's model */
#define STATUS_PIECES 0x160
#define PIECES_BODY 0xE8
#define PAIR_BODY 0                 /* a piece's pair [kind, 0, id]: kind 0 a body */

#define AT(base, offset, type) (*(type *)((base) + (offset)))

/* The actor `actor` takes body model `body`'s joints (0 or a model without joints: the actor's own). */
void felyne_body_joints(u8 *actor, const u8 *body)
{
    u8 *joints;
    const u8 *resource, *bones, *own = 0, *table = 0;
    u32 count, i;

    if (!actor || !(joints = AT(actor, MODEL_JOINTS, u8 *)) || !(resource = AT(actor, MODEL_RESOURCE, const u8 *)))
        return;
    bones = AT(resource, RESOURCE_BONES, const u8 *);
    count = AT(actor, MODEL_JOINT_COUNT, u32);
    if (body && (own = AT(body, MODEL_JOINTS, const u8 *)) != 0)
        table = AT(body, MODEL_JOINT_TABLE, const u8 *);
    for (i = 0; i < count; i++) {
        u8 *joint = joints + i * JOINT_SIZE;
        u32 number = joint[JOINT_NUMBER];
        const u32 *place = (const u32 *)(bones + i * BONE_SIZE + BONE_PLACE);
        u32 *rest = (u32 *)(joint + JOINT_REST);

        if (number == ROOT_JOINT)
            continue;
        if (table && table[number] != NO_JOINT)
            place = (const u32 *)(own + table[number] * JOINT_SIZE + JOINT_REST);
        rest[0] = place[0];
        rest[1] = place[1];
        rest[2] = place[2];
        rest[3] = 0;
    }
}

/* FUN_00697b00(manager, actor), a lobby cat whose body just loaded. */
void felyne_lobby_joints(u32 manager, u8 *actor)
{
    const u8 *pieces = AT(AT(actor, LOBBY_STATUS, const u8 *), STATUS_PIECES, const u8 *);

    (void)manager;
    felyne_body_joints(actor, AT(pieces, PIECES_BODY, const u8 *));
}

/* At FUN_00699d5c(manager, actor, model, pair)'s start, a quest cat's piece: a body's joints. */
void felyne_quest_joints(u32 manager, u8 *actor, const u8 *model, const u8 *pair)
{
    (void)manager;
    if (pair[0] == PAIR_BODY)
        felyne_body_joints(actor, model);
}
