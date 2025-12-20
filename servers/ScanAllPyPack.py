import os
import subprocess
import sys
import importlib.util
import re

def get_imported_packages(file_path):
    packages = set()
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
        content = file.read()
        # Match 'import package' or 'from package import ...'
        import_lines = re.findall(r'^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_.]*)', content, re.MULTILINE)
        for line in import_lines:
            # Split by dot and take only the first part (main package name)
            main_package = line.split('.')[0]
            # Clean any trailing commas or spaces
            main_package = main_package.strip().rstrip(',')
            if main_package:
                packages.add(main_package)
    return packages

def check_package_installed(package_name):
    spec = importlib.util.find_spec(package_name)
    return spec is not None

def install_package(package_name):
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package_name])
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to install {package_name}: {e}")
        return False

def get_package_dependencies(package_name):
    """Get common dependencies for a package"""
    # Dictionary of known dependencies
    dependencies = {
        'pandas': ['numpy', 'openpyxl', 'xlrd'],
        'qrcode': ['pillow', 'PIL'],
        'PIL': ['pillow'],
        'pillow': ['PIL']
    }
    return dependencies.get(package_name, [])

def scan_and_check_packages():
    current_folder = os.getcwd()
    python_files = []
    
    # Recursively scan all subfolders for Python files
    print(f"Scanning directory: {current_folder}")
    for root, dirs, files in os.walk(current_folder):
        for file in files:
            if file.endswith('.py') and file != os.path.basename(__file__):
                python_files.append(os.path.join(root, file))
    
    if not python_files:
        print("No Python files found in the current directory and subfolders.")
        return
    
    print(f"Found {len(python_files)} Python file(s) to scan.\n")
    
    all_required_packages = set()

    for file_path in python_files:
        # Get relative path for cleaner display
        rel_path = os.path.relpath(file_path, current_folder)
        print(f"Scanning file: {rel_path}")
        packages = get_imported_packages(file_path)
        all_required_packages.update(packages)

    # Remove standard library modules that don't need to be installed
    standard_libs = {
        'os', 'sys', 'json', 'argparse', 'datetime', 'subprocess', 
        're', 'pathlib', 'signal', 'io', 'collections', 'itertools',
        'functools', 'copy', 'math', 'random', 'time', 'threading'
    }
    all_required_packages -= standard_libs

    print(f"\nFound packages to check: {', '.join(sorted(all_required_packages))}")
    print("\nChecking package installations...")

    packages_to_install = set()

    for package in all_required_packages:
        if not check_package_installed(package):
            print(f"Package {package} is not installed.")
            packages_to_install.add(package)
        else:
            print(f"Package {package} is already installed.")
            
            # Check for common dependencies
            dependencies = get_package_dependencies(package)
            for dep in dependencies:
                if not check_package_installed(dep):
                    print(f"  Dependency {dep} for {package} is not installed.")
                    packages_to_install.add(dep)

    # Install missing packages
    if packages_to_install:
        print(f"\nInstalling missing packages: {', '.join(sorted(packages_to_install))}")
        for package in sorted(packages_to_install):
            # Skip if it's a standard lib or already installed
            if package in standard_libs:
                continue
            if check_package_installed(package):
                print(f"Package {package} is already installed.")
                continue
                
            print(f"Installing {package}...")
            if install_package(package):
                print(f"Successfully installed {package}")
            else:
                print(f"Failed to install {package}")
    else:
        print("\nAll required packages are already installed!")

if __name__ == "__main__":
    scan_and_check_packages()
# import os
# import subprocess
# import sys
# import importlib.util
# import re

# def get_imported_packages(file_path):
#     packages = set()
#     with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
#         content = file.read()
#         # Match 'import package' or 'from package import ...'
#         import_lines = re.findall(r'^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_.]*)', content, re.MULTILINE)
#         for line in import_lines:
#             # Split by dot and take only the first part (main package name)
#             main_package = line.split('.')[0]
#             # Clean any trailing commas or spaces
#             main_package = main_package.strip().rstrip(',')
#             if main_package:
#                 packages.add(main_package)
#     return packages

# def check_package_installed(package_name):
#     spec = importlib.util.find_spec(package_name)
#     return spec is not None

# def install_package(package_name):
#     try:
#         subprocess.check_call([sys.executable, '-m', 'pip', 'install', package_name])
#         return True
#     except subprocess.CalledProcessError as e:
#         print(f"Failed to install {package_name}: {e}")
#         return False

# def get_package_dependencies(package_name):
#     """Get common dependencies for a package"""
#     # Dictionary of known dependencies
#     dependencies = {
#         'pandas': ['numpy', 'openpyxl', 'xlrd'],
#         'qrcode': ['pillow', 'PIL'],
#         'PIL': ['pillow'],
#         'pillow': ['PIL']
#     }
#     return dependencies.get(package_name, [])

# def scan_and_check_packages():
#     current_folder = os.getcwd()
#     python_files = [f for f in os.listdir(current_folder) if f.endswith('.py') and f != os.path.basename(__file__)]
    
#     if not python_files:
#         print("No Python files found in the current directory.")
#         return
    
#     all_required_packages = set()

#     for py_file in python_files:
#         file_path = os.path.join(current_folder, py_file)
#         print(f"Scanning file: {py_file}")
#         packages = get_imported_packages(file_path)
#         all_required_packages.update(packages)

#     # Remove standard library modules that don't need to be installed
#     standard_libs = {
#         'os', 'sys', 'json', 'argparse', 'datetime', 'subprocess', 
#         're', 'pathlib', 'signal', 'io', 'collections', 'itertools',
#         'functools', 'copy', 'math', 'random', 'time', 'threading'
#     }
#     all_required_packages -= standard_libs

#     print(f"\nFound packages to check: {', '.join(sorted(all_required_packages))}")
#     print("\nChecking package installations...")

#     packages_to_install = set()

#     for package in all_required_packages:
#         if not check_package_installed(package):
#             print(f"Package {package} is not installed.")
#             packages_to_install.add(package)
#         else:
#             print(f"Package {package} is already installed.")
            
#             # Check for common dependencies
#             dependencies = get_package_dependencies(package)
#             for dep in dependencies:
#                 if not check_package_installed(dep):
#                     print(f"  Dependency {dep} for {package} is not installed.")
#                     packages_to_install.add(dep)

#     # Install missing packages
#     if packages_to_install:
#         print(f"\nInstalling missing packages: {', '.join(sorted(packages_to_install))}")
#         for package in sorted(packages_to_install):
#             # Skip if it's a standard lib or already installed
#             if package in standard_libs:
#                 continue
#             if check_package_installed(package):
#                 print(f"Package {package} is already installed.")
#                 continue
                
#             print(f"Installing {package}...")
#             if install_package(package):
#                 print(f"Successfully installed {package}")
#             else:
#                 print(f"Failed to install {package}")
#     else:
#         print("\nAll required packages are already installed!")

# if __name__ == "__main__":
#     scan_and_check_packages()
