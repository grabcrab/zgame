#!/usr/bin/env python3
"""
Setup script for Zombie Game application
Prepares the directory structure and copies template files
"""

import os
import shutil
from pathlib import Path


def create_directory_structure():
    """Create necessary directories"""
    directories = ['templates', 'static']
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"✓ Created directory: {directory}/")


def copy_template_files():
    """Copy template files from uploads to templates directory"""
    template_files = {
        'main.html': 'main.html',
        'prepare.html': 'prepare.html',
        'game.html': 'game.html',
        'end.html': 'end.html'
    }
    
    # Check if we're in a directory with uploads
    uploads_dir = Path('/mnt/user-data/uploads')
    if uploads_dir.exists():
        source_dir = uploads_dir
        print("Using uploaded files...")
    else:
        print("No uploaded files found. Please manually copy HTML files to templates/")
        return False
    
    templates_dir = Path('templates')
    success_count = 0
    
    for source_name, dest_name in template_files.items():
        source_file = source_dir / source_name
        dest_file = templates_dir / dest_name
        
        if source_file.exists():
            shutil.copy2(source_file, dest_file)
            print(f"✓ Copied {source_name} -> templates/{dest_name}")
            success_count += 1
        else:
            print(f"✗ File not found: {source_name}")
    
    return success_count == len(template_files)


def create_placeholder_logo():
    """Create a simple placeholder for logo if it doesn't exist"""
    logo_path = Path('static/logo.png')
    
    if not logo_path.exists():
        print("ℹ Logo file not found. Add your logo.png to static/ directory")
        # Create a placeholder file
        logo_path.touch()
        print("✓ Created placeholder logo file")


def check_dependencies():
    """Check if required Python packages are installed"""
    required_packages = ['flask', 'PyQt6']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.lower())
            print(f"✓ {package} is installed")
        except ImportError:
            missing_packages.append(package)
            print(f"✗ {package} is NOT installed")
    
    if missing_packages:
        print("\nTo install missing packages, run:")
        print("pip install -r requirements.txt")
        return False
    
    return True


def main():
    """Main setup function"""
    print("=" * 60)
    print("Zombie Game - Application Setup")
    print("=" * 60)
    print()
    
    # Create directories
    print("1. Creating directory structure...")
    create_directory_structure()
    print()
    
    # Copy template files
    print("2. Copying template files...")
    templates_ok = copy_template_files()
    print()
    
    # Create placeholder logo
    print("3. Checking static files...")
    create_placeholder_logo()
    print()
    
    # Check dependencies
    print("4. Checking Python dependencies...")
    deps_ok = check_dependencies()
    print()
    
    # Final status
    print("=" * 60)
    print("Setup Complete!")
    print("=" * 60)
    
    if templates_ok and deps_ok:
        print("\n✓ All checks passed!")
        print("\nTo run the application:")
        print("  python zombie_game_app.py")
    else:
        print("\n⚠ Some issues were found:")
        if not templates_ok:
            print("  - Template files need to be copied to templates/")
        if not deps_ok:
            print("  - Python dependencies need to be installed")
        print("\nPlease resolve these issues before running the application.")
    
    print()


if __name__ == '__main__':
    main()
