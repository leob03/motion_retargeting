def extract_joint_names(bvh_file_path):
    joint_names = []
    with open(bvh_file_path, 'r') as file:
        lines = file.readlines()
        for line in lines:
            line = line.strip()
            if line.startswith("JOINT") or line.startswith("ROOT"):
                # Extract the joint name after "JOINT" or "ROOT"
                joint_name = line.split()[1]
                joint_names.append(joint_name)
    return joint_names

# Example usage
if __name__ == "__main__":
    bvh_file_path = 'bvh_files/freemocap_whole_rearranged.bvh'
    fbx_file_path = 'fbx_files/fbx2bvh/Mixamo_Mannequin/Mixamo_Mannequin.bvh'
    joint_names = extract_joint_names(bvh_file_path)
    print(joint_names) 
    print(len(joint_names))
    joint_names_fbx = extract_joint_names(fbx_file_path)
    print(joint_names_fbx) 
    print(len(joint_names_fbx))