import bpy
import os
import gc

from bpy_extras.io_utils import (
    axis_conversion,
)
from mathutils import Matrix, Euler
from math import degrees

def write_armature(
        armature,
        filepath,
        frame_start,
        frame_end,
        global_scale=1.0,
        rotate_mode='NATIVE',
        root_transform_only=False,
        global_matrix=None,
        add_rest_pose_as_first_frame = False,
):

    def ensure_rot_order(rot_order_str):
        if set(rot_order_str) != {'X', 'Y', 'Z'}:
            rot_order_str = "XYZ"
        return rot_order_str

    file = open(filepath, "w", encoding="utf8", newline="\n")

    obj = armature
    arm = obj.data

    # Build a dictionary of children.
    # None for parentless
    children = {None: []}

    # initialize with blank lists
    for bone in arm.bones:
        children[bone.name] = []

    # keep bone order from armature, no sorting, not esspential but means
    # we can maintain order from import -> export which secondlife incorrectly expects.
    for bone in arm.bones:
        children[getattr(bone.parent, "name", None)].append(bone.name)

    # bone name list in the order that the bones are written
    serialized_names = []

    node_locations = {}

    # global_matrix: from current Blender coordinates system to output coordinates system 
    if global_matrix:
        global_matrix_inv = global_matrix.inverted()
        global_matrix_3x3 = global_matrix.to_3x3()

    file.write("HIERARCHY\n")

    def write_recursive_nodes(bone_name, indent):
        my_children = children[bone_name]

        indent_str = "\t" * indent

        bone = arm.bones[bone_name]
        pose_bone = obj.pose.bones[bone_name]
        loc = bone.head_local
        node_locations[bone_name] = loc

        if rotate_mode == "NATIVE":
            rot_order_str = ensure_rot_order(pose_bone.rotation_mode)
        else:
            rot_order_str = rotate_mode

        # make relative if we can
        if bone.parent:
            loc = loc - node_locations[bone.parent.name]

        if indent:
            file.write("%sJOINT %s\n" % (indent_str, bone_name))
        else:
            file.write("%sROOT %s\n" % (indent_str, bone_name))

        file.write("%s{\n" % indent_str)

        # global_matrix: from current Blender coordinates system to output coordinates system 
        if global_matrix:
            loc = global_matrix_3x3 @ loc

        file.write("%s\tOFFSET %.6f %.6f %.6f\n" % (indent_str, *(loc * global_scale)))
        if (bone.use_connect or root_transform_only) and bone.parent:
            file.write("%s\tCHANNELS 3 %srotation %srotation %srotation\n" % (indent_str, *rot_order_str))
        else:
            file.write("%s\tCHANNELS 6 Xposition Yposition Zposition %srotation %srotation %srotation\n" % (indent_str, *rot_order_str))

        if my_children:
            # store the location for the children
            # to get their relative offset

            # Write children
            for child_bone in my_children:
                serialized_names.append(child_bone)
                write_recursive_nodes(child_bone, indent + 1)

        else:
            # Write the bone end.
            file.write("%s\tEnd Site\n" % indent_str)
            file.write("%s\t{\n" % indent_str)
            loc = bone.tail_local - node_locations[bone_name]

            # global_matrix: from current Blender coordinates system to output coordinates system 
            if global_matrix:
                loc = global_matrix_3x3 @ loc

            file.write("%s\t\tOFFSET %.6f %.6f %.6f\n" % (indent_str, *(loc * global_scale)))
            file.write("%s\t}\n" % indent_str)

        file.write("%s}\n" % indent_str)

    if len(children[None]) == 1:
        key = children[None][0]
        serialized_names.append(key)
        indent = 0

        write_recursive_nodes(key, indent)

    else:
        # Write a dummy parent node, with a dummy key name
        # Just be sure it's not used by another bone!
        i = 0
        key = "__%d" % i
        while key in children:
            i += 1
            key = "__%d" % i
        file.write("ROOT %s\n" % key)
        file.write("{\n")
        file.write("\tOFFSET 0.0 0.0 0.0\n")
        file.write("\tCHANNELS 0\n")  # Xposition Yposition Zposition Xrotation Yrotation Zrotation
        indent = 1

        # Write children
        for child_bone in children[None]:
            serialized_names.append(child_bone)
            write_recursive_nodes(child_bone, indent)

        file.write("}\n")

    # redefine bones as sorted by serialized_names
    # so we can write motion

    class DecoratedBone:
        __slots__ = (
            # Bone name, used as key in many places.
            "name",
            "parent",  # decorated bone parent, set in a later loop
            # Blender armature bone.
            "rest_bone",
            # Blender pose bone.
            "pose_bone",
            # Blender pose matrix.
            "pose_mat",
            # Blender rest matrix (armature space).
            "rest_arm_mat",
            # Blender rest matrix (local space).
            "rest_local_mat",
            # Pose_mat inverted.
            "pose_imat",
            # Rest_arm_mat inverted.
            "rest_arm_imat",
            # Rest_local_mat inverted.
            "rest_local_imat",
            # Last used euler to preserve euler compatibility in between keyframes.
            "prev_euler",
            # Is the bone disconnected to the parent bone?
            "skip_position",
            "rot_order",
            "rot_order_str",
            # Needed for the euler order when converting from a matrix.
            "rot_order_str_reverse",
        )

        _eul_order_lookup = {
            'XYZ': (0, 1, 2),
            'XZY': (0, 2, 1),
            'YXZ': (1, 0, 2),
            'YZX': (1, 2, 0),
            'ZXY': (2, 0, 1),
            'ZYX': (2, 1, 0),
        }

        def __init__(self, bone_name):
            self.name = bone_name
            self.rest_bone = arm.bones[bone_name]
            self.pose_bone = obj.pose.bones[bone_name]

            if rotate_mode == "NATIVE":
                self.rot_order_str = ensure_rot_order(self.pose_bone.rotation_mode)
            else:
                self.rot_order_str = rotate_mode
            self.rot_order_str_reverse = self.rot_order_str[::-1]

            self.rot_order = DecoratedBone._eul_order_lookup[self.rot_order_str]

            self.pose_mat = self.pose_bone.matrix

            # mat = self.rest_bone.matrix  # UNUSED
            self.rest_arm_mat = self.rest_bone.matrix_local
            self.rest_local_mat = self.rest_bone.matrix

            # inverted mats
            self.pose_imat = self.pose_mat.inverted()
            self.rest_arm_imat = self.rest_arm_mat.inverted()
            self.rest_local_imat = self.rest_local_mat.inverted()

            self.parent = None
            self.prev_euler = Euler((0.0, 0.0, 0.0), self.rot_order_str_reverse)
            self.skip_position = ((self.rest_bone.use_connect or root_transform_only) and self.rest_bone.parent)

        def update_posedata(self):
            self.pose_mat = self.pose_bone.matrix
            self.pose_imat = self.pose_mat.inverted()

        def __repr__(self):
            if self.parent:
                return "[\"%s\" child on \"%s\"]\n" % (self.name, self.parent.name)
            else:
                return "[\"%s\" root bone]\n" % (self.name)

    bones_decorated = [DecoratedBone(bone_name) for bone_name in serialized_names]

    # Assign parents
    bones_decorated_dict = {dbone.name: dbone for dbone in bones_decorated}
    for dbone in bones_decorated:
        parent = dbone.rest_bone.parent
        if parent:
            dbone.parent = bones_decorated_dict[parent.name]
    del bones_decorated_dict
    # finish assigning parents

    scene = bpy.context.scene
    frame_current = scene.frame_current
    num_frames = frame_end - frame_start + 1
    if add_rest_pose_as_first_frame:
        num_frames += 1

    file.write("MOTION\n")
    file.write("Frames: %d\n" % (num_frames))
    file.write("Frame Time: %.6f\n" % (1.0 / (scene.render.fps)))

    if add_rest_pose_as_first_frame:
        for dbone in bones_decorated:
            if not dbone.skip_position:
                file.write("%.6f %.6f %.6f " % (0, 0, 0))

            file.write("%.6f %.6f %.6f " % (0, 0, 0))

        file.write("\n")

    for frame in range(frame_start, frame_end+1):
        scene.frame_set(frame)

        for dbone in bones_decorated:
            dbone.update_posedata()

        for dbone in bones_decorated:
            trans = Matrix.Translation(dbone.rest_bone.head_local)
            itrans = Matrix.Translation(-dbone.rest_bone.head_local)

            if dbone.parent:
                mat_final = dbone.parent.rest_arm_mat @ dbone.parent.pose_imat @ dbone.pose_mat @ dbone.rest_arm_imat
                mat_final = itrans @ mat_final @ trans
                loc = mat_final.to_translation() + (dbone.rest_bone.head_local - dbone.parent.rest_bone.head_local)
            else:
                mat_final = dbone.pose_mat @ dbone.rest_arm_imat
                mat_final = itrans @ mat_final @ trans
                loc = mat_final.to_translation() + dbone.rest_bone.head

            # global_matrix: from current Blender coordinates system to output coordinates system 
            if global_matrix:
                loc = global_matrix_3x3 @ loc
                mat_final = global_matrix @ mat_final @ global_matrix_inv

            # keep eulers compatible, no jumping on interpolation.
            rot = mat_final.to_euler(dbone.rot_order_str_reverse, dbone.prev_euler)

            if not dbone.skip_position:
                file.write("%.6f %.6f %.6f " % (loc * global_scale)[:])

            file.write("%.6f %.6f %.6f " % (degrees(rot[dbone.rot_order[0]]), degrees(rot[dbone.rot_order[1]]), degrees(rot[dbone.rot_order[2]])))

            dbone.prev_euler = rot

        file.write("\n")

    file.close()

    scene.frame_set(frame_current)

    print("BVH Exported: %s frames:%d\n" % (filepath, frame_end - frame_start + 1))


def save(
        armature, filepath="",
        frame_start=-1,
        frame_end=-1,
        global_scale=1.0,
        rotate_mode="NATIVE",
        root_transform_only=True,
        global_matrix=None,
        add_rest_pose_as_first_frame = False,
):
    # global_matrix: from current Blender coordinates system to output coordinates system 
    write_armature(
        armature, filepath,
        frame_start=frame_start,
        frame_end=frame_end,
        global_scale=global_scale,
        rotate_mode=rotate_mode,
        root_transform_only=root_transform_only,
        global_matrix=global_matrix,
        add_rest_pose_as_first_frame = add_rest_pose_as_first_frame,
    )

    return {'FINISHED'}


def clean_blocks():
    for c in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.unlink(c)
    
    for c in bpy.data.collections:
        bpy.data.collections.remove(c)
        
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)

    for block in bpy.data.materials:
        if block.users == 0:
            bpy.data.materials.remove(block)

    for block in bpy.data.textures:
        if block.users == 0:
            bpy.data.textures.remove(block)

    for block in bpy.data.images:
        if block.users == 0:
            bpy.data.images.remove(block)

def adjust_to_floor(armature):
    """Adjust the armature so that the lowest point touches the floor."""
    # Assuming the 'Hips' bone is the root and should be adjusted
    bone_name = 'Hips'
    bone = armature.pose.bones[bone_name]
    
    # Calculate the lowest point of the armature
    min_z = min((bone.head.z for bone in armature.pose.bones), default=0)
    
    # Calculate the offset needed to bring the lowest point to z=0 (floor level)
    offset_z = -min_z
    
    # Apply the offset to the root bone
    armature.data.bones[bone_name].select = True
    armature.data.bones.active = armature.data.bones[bone_name]
    bpy.ops.transform.translate(value=(0, 0, offset_z), orient_type='GLOBAL')
    armature.data.bones[bone_name].select = False

if __name__ == '__main__':
    
    bvh_folders = '/home/innovation/dev-lbringer/retargeting/motion_retargeting/source_motion'
    retargeted_bvh_folders = '/home/innovation/dev-lbringer/retargeting/motion_retargeting/target_motion'
    retargeted_Tpose_path = '/home/innovation/dev-lbringer/retargeting/motion_retargeting/source_Tpose/Mixamo_Mannequin.bvh'
    mixamo_fbx_path = '/home/innovation/dev-lbringer/retargeting/motion_retargeting/source_Tpose/Mixamo_Mannequin.fbx'

    
    bpy.context.scene.render.fps = 60
    
    if not os.path.exists(retargeted_bvh_folders):
        os.makedirs(retargeted_bvh_folders)

    bvh_files = os.listdir(bvh_folders)
    bvh_file_paths = [os.path.join(bvh_folders, bvh_file) for bvh_file in bvh_files if '.bvh' in bvh_file]

    for file_idx, bvh_file in enumerate(bvh_file_paths):
        if '.bvh' not in bvh_file:
            continue
        bvh_file_name = bvh_file.split('/')[-1]
        print('(%d/%d)Processing... %s' % (file_idx, len(bvh_file_paths), bvh_file_name))
        
        export_path = os.path.join(retargeted_bvh_folders, bvh_file_name)

        # Instead of deleting all objects, only delete those that are not marked as retargetted.
        bpy.ops.object.select_all(action='DESELECT')
        for obj in bpy.context.scene.objects:
            if not obj.get("retargetted", False):
                obj.select_set(True)
        bpy.ops.object.delete()

        bpy.ops.outliner.orphans_purge()
        clean_blocks()
        gc.collect()

        bpy.ops.import_anim.bvh(filepath=bvh_file)
        source_armature = bpy.context.object
        source_armature["retargetted"] = True  # Mark the input rig so it's preserved in subsequent iterations

        action = source_armature.animation_data.action

        start_frame = int(action.frame_range[0])
        end_frame = int(action.frame_range[1])
        bpy.context.scene.source_rig = source_armature.name

        bpy.ops.import_anim.bvh(filepath=retargeted_Tpose_path)
        target_armature = bpy.context.object 
        bpy.context.scene.target_rig = target_armature.name
        target_armature["retargetted"] = True  # Mark this armature so it's preserved in subsequent iterations

        bpy.ops.arp.auto_scale()
        bpy.ops.arp.build_bones_list()
        bpy.ops.arp.import_config_preset(preset_name='100style2mixamo_mannequin')
        
        bpy.ops.arp.redefine_rest_spose()

        # refine the T-pose
        armature = bpy.context.object
        
        bone_name = 'Hips'
        armature.data.bones[bone_name].select = True
        armature.data.bones.active = armature.data.bones[bone_name]
        bpy.ops.transform.translate(value=(-0, -0, -9), orient_type='GLOBAL', orient_matrix=((1, 0, 0), (0, 1, 0), (0, 0, 1)), orient_matrix_type='GLOBAL', constraint_axis=(False, False, True), mirror=False, snap=False, snap_elements={'INCREMENT'}, use_snap_project=False, snap_target='CLOSEST', use_snap_self=True, use_snap_edit=True, use_snap_nonedit=True, use_snap_selectable=False, release_confirm=True)
        armature.data.bones[bone_name].select = False
        
        bone_name = 'LeftKnee'
        armature.data.bones[bone_name].select = True
        armature.data.bones.active = armature.data.bones[bone_name]
        bpy.ops.transform.rotate(value=0.053, orient_axis='X', orient_type='GLOBAL', orient_matrix=((1, 0, 0), (0, 1, 0), (0, 0, 1)), orient_matrix_type='GLOBAL', constraint_axis=(True, False, False), mirror=False, snap=False, snap_elements={'INCREMENT'}, use_snap_project=False, snap_target='CLOSEST', use_snap_self=True, use_snap_edit=True, use_snap_nonedit=True, use_snap_selectable=False, release_confirm=True)
        armature.data.bones[bone_name].select = False

        bone_name = 'RightKnee'
        armature.data.bones[bone_name].select = True
        armature.data.bones.active = armature.data.bones[bone_name]
        bpy.ops.transform.rotate(value=0.053, orient_axis='X', orient_type='GLOBAL', orient_matrix=((1, 0, 0), (0, 1, 0), (0, 0, 1)), orient_matrix_type='GLOBAL', constraint_axis=(True, False, False), mirror=False, snap=False, snap_elements={'INCREMENT'}, use_snap_project=False, snap_target='CLOSEST', use_snap_self=True, use_snap_edit=True, use_snap_nonedit=True, use_snap_selectable=False, release_confirm=True)
        armature.data.bones[bone_name].select = False

        bone_name = 'Chest'
        armature.data.bones[bone_name].select = True
        armature.data.bones.active = armature.data.bones[bone_name]
        bpy.ops.transform.rotate(value=-0.125, orient_axis='X', orient_type='GLOBAL', orient_matrix=((1, 0, 0), (0, 1, 0), (0, 0, 1)), orient_matrix_type='GLOBAL', constraint_axis=(True, False, False), mirror=False, snap=False, snap_elements={'INCREMENT'}, use_snap_project=False, snap_target='CLOSEST', use_snap_self=True, use_snap_edit=True, use_snap_nonedit=True, use_snap_selectable=False, release_confirm=True)
        armature.data.bones[bone_name].select = False

        bone_name = 'Neck'
        armature.data.bones[bone_name].select = True
        armature.data.bones.active = armature.data.bones[bone_name]
        bpy.ops.transform.rotate(value=0.29, orient_axis='X', orient_type='GLOBAL', orient_matrix=((1, 0, 0), (0, 1, 0), (0, 0, 1)), orient_matrix_type='GLOBAL', constraint_axis=(True, False, False), mirror=False, snap=False, snap_elements={'INCREMENT'}, use_snap_project=False, snap_target='CLOSEST', use_snap_self=True, use_snap_edit=True, use_snap_nonedit=True, use_snap_selectable=False, release_confirm=True)
        armature.data.bones[bone_name].select = False
        
        bone_name = 'Head'
        armature.data.bones[bone_name].select = True
        armature.data.bones.active = armature.data.bones[bone_name]
        bpy.ops.transform.rotate(value=0.12, orient_axis='X', orient_type='GLOBAL', orient_matrix=((1, 0, 0), (0, 1, 0), (0, 0, 1)), orient_matrix_type='GLOBAL', constraint_axis=(True, False, False), mirror=False, snap=False, snap_elements={'INCREMENT'}, use_snap_project=False, snap_target='CLOSEST', use_snap_self=True, use_snap_edit=True, use_snap_nonedit=True, use_snap_selectable=False, release_confirm=True)
        armature.data.bones[bone_name].select = False
    
        bpy.ops.arp.save_pose_rest()
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.arp.retarget(frame_start=start_frame, frame_end=end_frame)

        bpy.ops.object.select_all(action='DESELECT')

        target_armature.select_set(True)

        bpy.context.view_layer.objects.active = target_armature

        global_matrix = axis_conversion(
                    from_forward="-Z",
                    from_up="Y",
                ).to_4x4().inverted()
        
        # # Scale down the target armature by a factor of 10
        # target_armature.scale = (0.1, 0.1, 0.1)
        # bpy.context.view_layer.update()  # Update the scene to apply the scale

        save(target_armature, filepath=export_path, frame_start=start_frame, frame_end=end_frame, root_transform_only=True, global_matrix=global_matrix)

