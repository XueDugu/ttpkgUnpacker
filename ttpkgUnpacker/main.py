import os
import sys
import shutil
from controller.main import Main

def create_raw_packages_folder(js_folder):
    raw_packages_folder = os.path.join(js_folder, 'rawPackages')
    if not os.path.exists(raw_packages_folder):
        os.mkdir(raw_packages_folder)

def copy_files_to_raw_packages(js_folder, file_list):
    raw_packages_folder = os.path.join(js_folder, 'rawPackages')
    for file in file_list:
        file_path = os.path.join(js_folder, file)
        # 使用二进制模式复制文件
        with open(file_path, 'rb') as f:
            content = f.read()
        target_file_path = os.path.join(raw_packages_folder, file)
        # 使用二进制模式写入文件
        with open(target_file_path, 'wb') as f:
            f.write(content)

def run_and_delete_ttpkg_js_files(js_folder):
    # Create rawPackages folder if it doesn't exist
    create_raw_packages_folder(js_folder)

    # Print "OK" and wait for user input
    flag=0
    print("解包后的原文件会出现在在rawPackages中。")

    # 获取js文件夹中的所有文件名
    files = os.listdir(js_folder)
    
    # 存储需要处理的文件列表
    files_to_process = []
    
    # 遍历每个文件
    for file in files:
        file_path = os.path.join(js_folder, file)
        
        # 如果后缀为.pkg或.ttpkg.js，则将原文件复制到rawPackages文件夹中
        if file.endswith('.pkg') or file.endswith('.ttpkg.js'):
            files_to_process.append(file)
    
    # 复制文件到rawPackages文件夹
    copy_files_to_raw_packages(js_folder, files_to_process)

    # 遍历需要处理的文件列表
    for file in files_to_process:
        file_path = os.path.join(js_folder, file)
        flag=flag+1

        # 运行程序
        Main(["", file_path]).run()

        # 删除原文件
        os.remove(file_path)

    print("成功解包", end='')
    print(flag, end='')
    print("个文件!!!")

if __name__ == "__main__":
    # 使用input()函数提示用户输入js文件夹的路径
    js_folder = input("请输入需要解包的文件所在文件夹的路径:")

    # 检查用户输入的路径是否有效
    if not os.path.exists(js_folder):
        print("无效的文件夹路径！请重新运行并输入有效的路径。")
        sys.exit(1)

    run_and_delete_ttpkg_js_files(js_folder)

    # 程序运行结束后，等待用户按回车键终止
    input("按回车键结束程序...")

#1
# import sys
# from controller.main import Main
# file_path = ["","js/038d897.ttpkg.js"]
# Main(file_path).run()

#2
# import os
# from controller.main import Main
# def run_and_delete_ttpkg_js_files(js_folder):
#     # 获取js文件夹中的所有文件名
#     files = os.listdir(js_folder)
#     # 过滤出后缀为.ttpkg.js的文件
#     ttpkg_js_files = [file for file in files if file.endswith('.ttpkg.js')]
#     # 遍历运行每个.ttpkg.js文件
#     for file in ttpkg_js_files:
#         file_path = os.path.join(js_folder, file)
#         Main(["", file_path]).run()  # 运行Main类的run方法
#         # 删除.ttpkg.js文件
#         os.remove(file_path)
# if __name__ == "__main__":
#     js_folder = "js"  # 设置js文件夹的路径
#     run_and_delete_ttpkg_js_files(js_folder)

#3
# import os
# from controller.main import Main
# def run_and_delete_ttpkg_js_files(js_folder):
#     # Print "OK" and wait for user input
#     input("OK")
#     # 获取js文件夹中的所有文件名
#     files = os.listdir(js_folder)
#     # 遍历每个文件
#     for file in files:
#         file_path = os.path.join(js_folder, file)
#         # 如果后缀为.pkg，则将.pkg改为.ttpkg.js
#         if file.endswith('.pkg'):
#             new_file_path = file_path.replace('.pkg', '.ttpkg.js')
#             os.rename(file_path, new_file_path)
#             # 运行程序
#             Main(["", new_file_path]).run()
#             # 删除原文件
#             os.remove(new_file_path)
#         # 如果后缀为.ttpkg.js，则直接运行程序并删除原文件
#         elif file.endswith('.ttpkg.js'):
#             Main(["", file_path]).run()
#             os.remove(file_path)
# if __name__ == "__main__":
#     js_folder = "js"  # 设置js文件夹的路径
#     run_and_delete_ttpkg_js_files(js_folder)

#4
# import os
# import shutil
# from controller.main import Main
# def create_raw_packages_folder(js_folder):
#     raw_packages_folder = os.path.join(js_folder, 'rawPackages')
#     if not os.path.exists(raw_packages_folder):
#         os.mkdir(raw_packages_folder)
# def copy_files_to_raw_packages(js_folder, file_list):
#     raw_packages_folder = os.path.join(js_folder, 'rawPackages')
#     for file in file_list:
#         file_path = os.path.join(js_folder, file)
#         shutil.copy(file_path, raw_packages_folder)
# def run_and_delete_ttpkg_js_files(js_folder):
#     # Create rawPackages folder if it doesn't exist
#     create_raw_packages_folder(js_folder)
#     # Print "OK" and wait for user input
#     flag=0
#     print("解包后的原文件在rawPackages中。")
#     # 获取js文件夹中的所有文件名
#     files = os.listdir(js_folder)
#     # 存储需要处理的文件列表
#     files_to_process = []
#     # 遍历每个文件
#     for file in files:
#         file_path = os.path.join(js_folder, file)
#         # 如果后缀为.pkg或.ttpkg.js，则将原文件复制到rawPackages文件夹中
#         if file.endswith('.pkg') or file.endswith('.ttpkg.js'):
#             files_to_process.append(file)
#     # 复制文件到rawPackages文件夹
#     copy_files_to_raw_packages(js_folder, files_to_process)
#     # 遍历需要处理的文件列表
#     for file in files_to_process:
#         file_path = os.path.join(js_folder, file)
#         flag=flag+1
#         # 运行程序
#         Main(["", file_path]).run()
#         # 删除原文件
#         os.remove(file_path)
#     print("成功解包", end='')
#     print(flag, end='')
#     print("个文件!!!")
# if __name__ == "__main__":
#     js_folder = "js"  # 设置js文件夹的路径
#     run_and_delete_ttpkg_js_files(js_folder)

#5
# import os
# import sys
# import shutil
# from controller.main import Main
# def create_raw_packages_folder(js_folder):
#     raw_packages_folder = os.path.join(js_folder, 'rawPackages')
#     if not os.path.exists(raw_packages_folder):
#         os.mkdir(raw_packages_folder)
# def copy_files_to_raw_packages(js_folder, file_list):
#     raw_packages_folder = os.path.join(js_folder, 'rawPackages')
#     for file in file_list:
#         file_path = os.path.join(js_folder, file)
#         shutil.copy(file_path, raw_packages_folder)
# def run_and_delete_ttpkg_js_files(js_folder):
#     # Create rawPackages folder if it doesn't exist
#     create_raw_packages_folder(js_folder)
#     # Print "OK" and wait for user input
#     flag=0
#     print("解包后的原文件在rawPackages中。")
#     # 获取js文件夹中的所有文件名
#     files = os.listdir(js_folder)
#     # 存储需要处理的文件列表
#     files_to_process = []
#     # 遍历每个文件
#     for file in files:
#         file_path = os.path.join(js_folder, file)
#         # 如果后缀为.pkg或.ttpkg.js，则将原文件复制到rawPackages文件夹中
#         if file.endswith('.pkg') or file.endswith('.ttpkg.js'):
#             files_to_process.append(file)
#     # 复制文件到rawPackages文件夹
#     copy_files_to_raw_packages(js_folder, files_to_process)
#     # 遍历需要处理的文件列表
#     for file in files_to_process:
#         file_path = os.path.join(js_folder, file)
#         flag=flag+1
#         # 运行程序
#         Main(["", file_path]).run()
#         # 删除原文件
#         os.remove(file_path)
#     print("成功解包", end='')
#     print(flag, end='')
#     print("个文件!!!")
# if __name__ == "__main__":
#     # 获取命令行参数，即js文件夹的路径
#     if len(sys.argv) != 2:
#         print("Usage: python script_name.py <js_folder_path>")
#         sys.exit(1)
#     js_folder = sys.argv[1]  # 设置js文件夹的路径
#     run_and_delete_ttpkg_js_files(js_folder)
