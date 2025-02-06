bl_info = {
    "name": "Batch Retargeting Add-on",
    "author": "Leo Bringer",
    "version": (1, 0),
    "blender": (4, 2, 3),  # or whichever version you're targeting
    "location": "3D View > Sidebar > Animation Tab",
    "description": "Performs batch retargeting of BVH files to a specific rigs and associated meshes through ARP operators",
    "warning": "",
    "category": "Batch Retargeting",
}

import bpy
import os
import gc

from mathutils import Matrix, Euler
from math import degrees
from bpy.props import (
    StringProperty,
    IntProperty,
    PointerProperty
)
from bpy_extras.io_utils import axis_conversion

# ------------------------------------------------------------------------
# 1. Helper Functions (same as your script)
# ------------------------------------------------------------------------

def ensure_rot_order(rot_order_str):
    """Ensure rotation order is a combination of X/Y/Z only, else fallback to 'XYZ'."""
    if set(rot_order_str) != {'X', 'Y', 'Z'}:
        rot_order_str = "XYZ"
    return rot_order_str

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

    file = open(filepath, "w", encoding="utf8", newline="\n")

    obj = armature
    arm = obj.data

    # Build a dictionary of children
    children = {None: []}
    for bone in arm.bones:
        children[bone.name] = []
    for bone in arm.bones:
        parent_name = bone.parent.name if bone.parent else None
        children[parent_name].append(bone.name)

    serialized_names = []
    node_locations = {}

    # Matrix precomputation if needed
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

        # Make relative location
        if bone.parent:
            loc = loc - node_locations[bone.parent.name]

        if indent:
            file.write("%sJOINT %s\n" % (indent_str, bone_name))
        else:
            file.write("%sROOT %s\n" % (indent_str, bone_name))
        file.write("%s{\n" % indent_str)

        if global_matrix:
            loc = global_matrix_3x3 @ loc

        file.write("%s\tOFFSET %.6f %.6f %.6f\n" % (indent_str, *(loc * global_scale)))
        if (bone.use_connect or root_transform_only) and bone.parent:
            file.write("%s\tCHANNELS 3 %srotation %srotation %srotation\n" % (indent_str, *rot_order_str))
        else:
            file.write("%s\tCHANNELS 6 Xposition Yposition Zposition %srotation %srotation %srotation\n" % (indent_str, *rot_order_str))

        if my_children:
            for child_bone in my_children:
                serialized_names.append(child_bone)
                write_recursive_nodes(child_bone, indent + 1)
        else:
            # Bone end
            file.write("%s\tEnd Site\n" % indent_str)
            file.write("%s\t{\n" % indent_str)
            loc = bone.tail_local - node_locations[bone_name]
            if global_matrix:
                loc = global_matrix_3x3 @ loc
            file.write("%s\t\tOFFSET %.6f %.6f %.6f\n" % (indent_str, *(loc * global_scale)))
            file.write("%s\t}\n" % indent_str)

        file.write("%s}\n" % indent_str)

    # Write root
    if len(children[None]) == 1:
        key = children[None][0]
        serialized_names.append(key)
        write_recursive_nodes(key, 0)
    else:
        # If multiple root bones exist, wrap them in a dummy root
        i = 0
        key = "__%d" % i
        while key in children:
            i += 1
            key = "__%d" % i
        file.write("ROOT %s\n" % key)
        file.write("{\n")
        file.write("\tOFFSET 0.0 0.0 0.0\n")
        file.write("\tCHANNELS 0\n")
        indent = 1
        for child_bone in children[None]:
            serialized_names.append(child_bone)
            write_recursive_nodes(child_bone, indent)
        file.write("}\n")

    class DecoratedBone:
        __slots__ = (
            "name",
            "parent",
            "rest_bone",
            "pose_bone",
            "pose_mat",
            "rest_arm_mat",
            "rest_local_mat",
            "pose_imat",
            "rest_arm_imat",
            "rest_local_imat",
            "prev_euler",
            "skip_position",
            "rot_order",
            "rot_order_str",
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
            self.rest_arm_mat = self.rest_bone.matrix_local
            self.rest_local_mat = self.rest_bone.matrix

            self.pose_imat = self.pose_mat.inverted()
            self.rest_arm_imat = self.rest_arm_mat.inverted()
            self.rest_local_imat = self.rest_local_mat.inverted()

            self.parent = None
            self.prev_euler = Euler((0.0, 0.0, 0.0), self.rot_order_str_reverse)
            self.skip_position = ((self.rest_bone.use_connect or root_transform_only) and self.rest_bone.parent)

        def update_posedata(self):
            self.pose_mat = self.pose_bone.matrix
            self.pose_imat = self.pose_mat.inverted()

    bones_decorated = [DecoratedBone(bone_name) for bone_name in serialized_names]

    # Assign parents
    bones_decorated_dict = {dbone.name: dbone for dbone in bones_decorated}
    for dbone in bones_decorated:
        parent = dbone.rest_bone.parent
        if parent:
            dbone.parent = bones_decorated_dict[parent.name]
    del bones_decorated_dict

    scene = bpy.context.scene
    frame_current = scene.frame_current
    num_frames = frame_end - frame_start + 1
    if add_rest_pose_as_first_frame:
        num_frames += 1

    file.write("MOTION\n")
    file.write("Frames: %d\n" % (num_frames))
    file.write("Frame Time: %.6f\n" % (1.0 / (scene.render.fps)))

    # Optionally write the rest pose as the first frame
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
                mat_final = (dbone.parent.rest_arm_mat 
                             @ dbone.parent.pose_imat 
                             @ dbone.pose_mat 
                             @ dbone.rest_arm_imat)
                mat_final = itrans @ mat_final @ trans
                loc = mat_final.to_translation() + (
                    dbone.rest_bone.head_local - dbone.parent.rest_bone.head_local
                )
            else:
                mat_final = dbone.pose_mat @ dbone.rest_arm_imat
                mat_final = itrans @ mat_final @ trans
                loc = mat_final.to_translation() + dbone.rest_bone.head

            if global_matrix:
                loc = global_matrix_3x3 @ loc
                mat_final = global_matrix @ mat_final @ global_matrix_inv

            # keep eulers compatible
            rot = mat_final.to_euler(dbone.rot_order_str_reverse, dbone.prev_euler)

            if not dbone.skip_position:
                file.write("%.6f %.6f %.6f " % (loc[0], loc[1], loc[2]))
            file.write("%.6f %.6f %.6f " % (
                degrees(rot[dbone.rot_order[0]]),
                degrees(rot[dbone.rot_order[1]]),
                degrees(rot[dbone.rot_order[2]])
            ))
            dbone.prev_euler = rot
        file.write("\n")

    file.close()
    scene.frame_set(frame_current)
    print(f"BVH Exported: {filepath} frames: {frame_end - frame_start + 1}")


def save(
        armature, filepath="",
        frame_start=-1,
        frame_end=-1,
        global_scale=1.0,
        rotate_mode="NATIVE",
        root_transform_only=True,
        global_matrix=None,
        add_rest_pose_as_first_frame=False,
):
    """Simple wrapper that calls 'write_armature'."""
    write_armature(
        armature, filepath,
        frame_start=frame_start,
        frame_end=frame_end,
        global_scale=global_scale,
        rotate_mode=rotate_mode,
        root_transform_only=root_transform_only,
        global_matrix=global_matrix,
        add_rest_pose_as_first_frame=add_rest_pose_as_first_frame,
    )
    return {'FINISHED'}


def clean_blocks():
    """
    Cleans up data-blocks from the .blend file that have zero users.
    """
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
    """
    Adjust the armature so that the lowest point touches the floor (example usage).
    """
    bone_name = 'Hips'
    if bone_name not in armature.pose.bones:
        return
    # find the min z among all bones
    min_z = min((b.head.z for b in armature.pose.bones), default=0)
    offset_z = -min_z
    armature.data.bones[bone_name].select = True
    armature.data.bones.active = armature.data.bones[bone_name]
    bpy.ops.transform.translate(value=(0, 0, offset_z), orient_type='GLOBAL')
    armature.data.bones[bone_name].select = False

# ------------------------------------------------------------------------
# 2. Property Group to store hyperparameters
# ------------------------------------------------------------------------

class BATCHRETARGET_Properties(bpy.types.PropertyGroup):
    """
    Stores the user-editable hyperparameters that will appear in the panel.
    """
    bvh_folders: StringProperty(
        name="Source Motion BVH Folder",
        description="Folder containing source BVH motion files",
        default="/path/to/source_motion",
        subtype='DIR_PATH'
    )
    retargeted_bvh_folders: StringProperty(
        name="Retargeted BVH Folder",
        description="Folder to store exported BVH files",
        default="/path/to/target_motion",
        subtype='DIR_PATH'
    )
    mixamo_fbx_path: StringProperty(
        name="T-Pose Character FBX Path",
        description="Path to the T-Pose Character FBX used as target rig",
        default="/path/to/Tpose_Mannequin.fbx",
        subtype='FILE_PATH'
    )
    preset_name: StringProperty(
        name="ARP bmap Preset Name",
        description="Name of the ARP bmap preset",
        default="100style2mixamo_mannequin"
    )
    fps: IntProperty(
        name="FPS",
        description="Frames per second for the retargeted animation",
        default=60,
        min=1,
        max=240
    )

# ------------------------------------------------------------------------
# 3. Operator that performs the batch retarget
# ------------------------------------------------------------------------

class OBJECT_OT_batch_retarget(bpy.types.Operator):
    """
    Performs the batch retargeting using the hyperparameters from the panel.
    """
    bl_idname = "object.batch_retarget"
    bl_label = "Batch Retarget BVH Files"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.batch_retarget_props

        bvh_folders             = props.bvh_folders
        retargeted_bvh_folders = props.retargeted_bvh_folders
        mixamo_fbx_path         = props.mixamo_fbx_path
        preset_name             = props.preset_name
        fps                     = props.fps

        # Make sure target folder exists
        if not os.path.exists(retargeted_bvh_folders):
            os.makedirs(retargeted_bvh_folders)

        bpy.context.scene.render.fps = fps

        # Collect BVH files
        bvh_files = [f for f in os.listdir(bvh_folders) if f.lower().endswith(".bvh")]
        bvh_file_paths = [os.path.join(bvh_folders, bf) for bf in bvh_files]
        if not bvh_file_paths:
            self.report({'WARNING'}, "No BVH files found in folder: " + bvh_folders)

        for file_idx, bvh_file in enumerate(bvh_file_paths):
            bvh_file_name = os.path.split(bvh_file)[-1]
            self.report({'INFO'}, f"Processing {file_idx+1}/{len(bvh_file_paths)}: {bvh_file_name}")

            export_path = os.path.join(retargeted_bvh_folders, bvh_file_name)

            # Delete unmarked objects
            bpy.ops.object.select_all(action='DESELECT')
            for obj in bpy.context.scene.objects:
                if not obj.get("retargetted", False):
                    obj.select_set(True)
            bpy.ops.object.delete()

            # Purge orphans
            bpy.ops.outliner.orphans_purge()
            clean_blocks()
            gc.collect()

            # Import the source motion BVH
            bpy.ops.import_anim.bvh(filepath=bvh_file)
            source_armature = bpy.context.object
            source_armature["retargetted"] = True

            # Make the newly imported BVH armature active & set as ARP's source rig
            bpy.context.view_layer.objects.active = source_armature
            source_armature.select_set(True)
            bpy.context.scene.source_rig = source_armature.name

            # Figure out frames
            action = source_armature.animation_data.action
            start_frame = int(action.frame_range[0])
            end_frame   = int(action.frame_range[1])

            # Import the FBX target rig
            bpy.ops.import_scene.fbx(filepath=mixamo_fbx_path)
            target_armature = None
            for obj in bpy.context.selected_objects:
                if obj.type == 'ARMATURE':
                    target_armature = obj
                    break
            if target_armature is None:
                self.report({'ERROR'}, "No armature found in FBX!")
                return {'CANCELLED'}
            target_armature["retargetted"] = True

            # Make the newly imported FBX armature active & set as ARP's target rig
            bpy.context.view_layer.objects.active = target_armature
            target_armature.select_set(True)
            bpy.context.scene.target_rig = target_armature.name

            # Mark any imported meshes from FBX as retargetted
            for obj in bpy.context.selected_objects:
                if obj.type == 'MESH':
                    obj["retargetted"] = True

            # ARP pipeline
            bpy.ops.arp.auto_scale()
            bpy.ops.arp.build_bones_list()

            # Try to import your preset
            try:
                bpy.ops.arp.import_config_preset(preset_name=preset_name)
            except Exception as e:
                self.report({'WARNING'}, f"Preset '{preset_name}' not found. Check ARP preset names. ({e})")

            bpy.ops.arp.redefine_rest_pose()

            # (Optional) adjust-to-floor or other T-pose refinements:
            # adjust_to_floor(target_armature)

            bpy.ops.arp.save_pose_rest()
            bpy.ops.object.mode_set(mode='OBJECT')

            # Retarget using ARP
            bpy.ops.arp.retarget(frame_start=start_frame, frame_end=end_frame)

            # Export retargeted as BVH
            bpy.ops.object.select_all(action='DESELECT')
            global_matrix = axis_conversion(from_forward="-Z", from_up="Y").to_4x4().inverted()

            save(target_armature, filepath=export_path,
                 frame_start=start_frame, frame_end=end_frame,
                 root_transform_only=True,
                 global_matrix=global_matrix)

            self.report({'INFO'}, f"Exported retargeted BVH to: {export_path}")

        self.report({'INFO'}, "Batch Retargeting Finished!")
        return {'FINISHED'}

# ------------------------------------------------------------------------
# 4. Panel to display the properties & run operator
# ------------------------------------------------------------------------

class VIEW3D_PT_batch_retarget_panel(bpy.types.Panel):
    """
    A panel in the 3D View sidebar > Animation tab, for editing hyperparameters & retargeting.
    """
    bl_label = "Batch Retarget"
    bl_idname = "VIEW3D_PT_batch_retarget_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Batch Retargeting"

    def draw(self, context):
        layout = self.layout
        props = context.scene.batch_retarget_props

        layout.prop(props, "bvh_folders")
        layout.prop(props, "retargeted_bvh_folders")
        layout.prop(props, "mixamo_fbx_path")
        layout.prop(props, "preset_name")
        layout.prop(props, "fps")

        layout.operator("object.batch_retarget", text="Retarget")

# ------------------------------------------------------------------------
# 5. Registration
# ------------------------------------------------------------------------

classes = (
    BATCHRETARGET_Properties,
    OBJECT_OT_batch_retarget,
    VIEW3D_PT_batch_retarget_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    # Attach our custom property group to the Scene type
    bpy.types.Scene.batch_retarget_props = PointerProperty(type=BATCHRETARGET_Properties)

def unregister():
    del bpy.types.Scene.batch_retarget_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

# if __name__ == "__main__":
#     register()
