# Blender Batch Motion Retargeting Add-on

The Blender Batch Motion Retargeting Add-on is a powerful tool designed to streamline your animation workflow by automating the process of retargeting motion capture data. Built specifically for Blender and leveraging the capabilities of Auto-Rig Pro, this add-on allows you to convert entire directories of BVH files from one rig format to another—saving you countless hours of manual work. Additionally, if you supply a T-Pose FBX file, the add-on can also retarget associated mesh data for each generated motion sequence.

---

## Features

- **Batch Processing:** Retarget an entire directory of BVH files in one operation.
- **Rig Format Conversion:** Seamlessly convert motion data from one similar rig format to another.
- **Mesh Integration:** Optionally retarget mesh animations by using a supplied T-Pose FBX file.
- **Auto-Rig Pro Compatibility:** Fully integrated with [Auto-Rig Pro](https://blendermarket.com/products/auto-rig-pro) for enhanced rigging support.
- **User-Friendly Interface:** Intuitive controls within Blender to configure directories, files, and retargeting settings.
- **Time-Saving Automation:** Reduce repetitive tasks and focus more on the creative aspects of your animation projects.

---

## Prerequisites

- **Blender:** Compatible with Blender 3.x and above.
- **Auto-Rig Pro:** This add-on requires Auto-Rig Pro to be installed and activated. Purchase and download it from [Blender Market](https://blendermarket.com/products/auto-rig-pro). we use ARP 3.69.
- **Python:** Uses Blender’s bundled Python environment bpy for Python 3.10.

---

## Installation

1. **Download the Add-on:**
   - Get the latest release from the [Releases](#) section of this repository.

2. **Install in Blender:**
   - Open Blender and navigate to `Edit > Preferences > Add-ons > Install…`
   - Select the downloaded `.zip` file.
   - Enable the add-on by checking its box in the add-ons list.

3. **Configure Settings:**
   - Set up the source directory for your BVH files.
   - Define the target directory where the retargeted BVH files will be saved.
   - (Optional) Provide the path to your T-Pose FBX file if you need mesh retargeting.

---

## Usage

1. **Prepare Your Data:**
   - Organize your source BVH files in a dedicated directory.
   - Ensure you have a T-Pose FBX file ready if mesh retargeting is desired.

2. **Run the Retargeting Process:**
   - Open the add-on panel within Blender.
   - Specify your source and target directories.
   - (Optional) Input the T-Pose FBX file path.
   - Click the **Retarget** button to begin the batch process.

3. **Review and Refine:**
   - Once the process is complete, review the generated BVH files and mesh animations.
   - Use Blender’s animation tools to make any necessary adjustments.

