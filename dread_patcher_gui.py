#!/usr/bin/env python3
"""
Metroid Bread Archipelago Patcher GUI

A simple GUI tool to convert Archipelago spoiler files to patched Metroid Bread mods.
This streamlines the entire process into a few clicks!
"""

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from pathlib import Path
import json
import subprocess
import sys
import threading
import os

# Import the converter
from ap_to_patcher import create_patcher_json


class DreadPatcherGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Metroid Bread AP Patcher")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        # Variables
        self.spoiler_path = tk.StringVar()
        self.player_name = tk.StringVar()
        self.base_rom_path = tk.StringVar(value=r"C:\Users\dummy\Downloads\md rando")
        self.output_path = tk.StringVar(value=r"C:\Users\dummy\AppData\Roaming\Ryujinx\mods\contents\010093801237c000")
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the GUI layout"""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights for responsiveness
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(6, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="Metroid Bread Archipelago Patcher", 
                                font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Spoiler file selection
        row = 1
        ttk.Label(main_frame, text="Spoiler File:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.spoiler_path, width=50).grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
        ttk.Button(main_frame, text="Browse...", command=self.browse_spoiler).grid(row=row, column=2, pady=5)
        
        # Player name
        row += 1
        ttk.Label(main_frame, text="Player Name:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.player_name, width=50).grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
        ttk.Label(main_frame, text="(must match YAML)", font=('Arial', 8, 'italic')).grid(row=row, column=2, pady=5)
        
        # Base ROM path
        row += 1
        ttk.Label(main_frame, text="Base ROM Folder:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.base_rom_path, width=50).grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
        ttk.Button(main_frame, text="Browse...", command=self.browse_base_rom).grid(row=row, column=2, pady=5)
        
        # Output path
        row += 1
        ttk.Label(main_frame, text="Output Folder:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.output_path, width=50).grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
        ttk.Button(main_frame, text="Browse...", command=self.browse_output).grid(row=row, column=2, pady=5)
        
        # Action buttons
        row += 1
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=3, pady=20)
        
        self.patch_button = ttk.Button(button_frame, text="🎮 Generate & Patch", 
                                       command=self.run_patch, style='Accent.TButton')
        self.patch_button.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(button_frame, text="Clear Log", command=self.clear_log).pack(side=tk.LEFT, padx=5)
        
        # Progress bar
        row += 1
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        # Log output
        row += 1
        log_label = ttk.Label(main_frame, text="Output Log:")
        log_label.grid(row=row, column=0, sticky=tk.W, pady=(10, 5))
        
        row += 1
        self.log_text = scrolledtext.ScrolledText(main_frame, height=15, width=80, 
                                                   wrap=tk.WORD, font=('Consolas', 9))
        self.log_text.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Status bar
        row += 1
        self.status_label = ttk.Label(main_frame, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(10, 0))
        
        # Initial log message
        self.log("Metroid Bread Archipelago Patcher Ready!")
        self.log("1. Select your Archipelago spoiler file")
        self.log("2. Enter your player name (must match your YAML)")
        self.log("3. Click 'Generate & Patch' to create the mod")
        self.log("")
        
    def browse_spoiler(self):
        """Browse for spoiler file"""
        filename = filedialog.askopenfilename(
            title="Select Archipelago Spoiler File",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            self.spoiler_path.set(filename)
            self.log(f"Selected spoiler: {filename}")
            
            # Try to auto-detect player name from filename
            # Format: AP_12345_Spoiler.txt or similar
            try:
                path = Path(filename)
                # Look for yaml files in parent directory
                yaml_files = list(path.parent.glob("*.yaml"))
                if yaml_files and not self.player_name.get():
                    # Try to extract player name from yaml filename
                    yaml_name = yaml_files[0].stem
                    if "_" in yaml_name:
                        possible_name = yaml_name.split("_")[-1]
                        self.player_name.set(possible_name)
                        self.log(f"Auto-detected player name: {possible_name}")
            except Exception as e:
                pass
    
    def browse_base_rom(self):
        """Browse for base ROM folder"""
        folder = filedialog.askdirectory(title="Select Base ROM Folder")
        if folder:
            self.base_rom_path.set(folder)
            self.log(f"Base ROM: {folder}")
    
    def browse_output(self):
        """Browse for output folder"""
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_path.set(folder)
            self.log(f"Output: {folder}")
    
    def log(self, message):
        """Add message to log"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def clear_log(self):
        """Clear the log"""
        self.log_text.delete(1.0, tk.END)
    
    def set_status(self, message, color=None):
        """Update status bar"""
        self.status_label.config(text=message)
        if color:
            self.status_label.config(foreground=color)
        self.root.update_idletasks()
    
    def validate_inputs(self):
        """Validate all inputs before running"""
        errors = []
        
        if not self.spoiler_path.get():
            errors.append("Please select a spoiler file")
        elif not Path(self.spoiler_path.get()).exists():
            errors.append("Spoiler file does not exist")
        
        if not self.player_name.get():
            errors.append("Please enter your player name")
        
        if not self.base_rom_path.get():
            errors.append("Please select base ROM folder")
        elif not Path(self.base_rom_path.get()).exists():
            errors.append("Base ROM folder does not exist")
        
        if not self.output_path.get():
            errors.append("Please select output folder")
        
        return errors
    
    def run_patch(self):
        """Run the patching process"""
        # Validate inputs
        errors = self.validate_inputs()
        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors))
            return
        
        # Disable button during processing
        self.patch_button.config(state='disabled')
        self.progress.start(10)
        self.set_status("Processing...", "blue")
        
        # Run in thread to keep GUI responsive
        thread = threading.Thread(target=self._run_patch_thread)
        thread.daemon = True
        thread.start()
    
    def _run_patch_thread(self):
        """Thread worker for patching"""
        try:
            self.log("\n" + "="*70)
            self.log("STARTING PATCH PROCESS")
            self.log("="*70)
            
            # Step 1: Generate patcher.json
            self.log("\n[1/5] Converting spoiler to patcher.json...")
            temp_patcher = Path("temp_archipelago_patcher.json")
            
            # Load template
            template_path = Path("sample_patcher_WORKING.json")
            if not template_path.exists():
                raise FileNotFoundError("sample_patcher_WORKING.json not found!")
            
            with open(template_path) as f:
                template = json.load(f)
            
            # Create patcher data
            patcher_data = create_patcher_json(
                Path(self.spoiler_path.get()),
                self.player_name.get(),
                template
            )
            
            # Save temp patcher file
            with open(temp_patcher, 'w') as f:
                json.dump(patcher_data, f, indent=2)
            
            self.log(f"✓ Generated: {temp_patcher}")
            self.log(f"  Pickups: {len(patcher_data['pickups'])}")
            self.log(f"  Layout UUID: {patcher_data['layout_uuid']}")
            
            # Step 2: Run open-dread-rando patcher
            self.log("\n[2/5] Running open-dread-rando patcher...")
            self.log("This may take 30-60 seconds...")
            
            cmd = [
                sys.executable,
                "-m", "open_dread_rando",
                "--input-json", str(temp_patcher),
                "--input-path", self.base_rom_path.get(),
                "--output-path", self.output_path.get()
            ]
            
            self.log(f"Command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            # Log output
            if result.stdout:
                for line in result.stdout.split('\n'):
                    if line.strip():
                        self.log(f"  {line}")
            
            if result.returncode != 0:
                self.log("\n❌ ERROR during patching:")
                if result.stderr:
                    for line in result.stderr.split('\n'):
                        if line.strip():
                            self.log(f"  {line}")
                raise Exception(f"Patcher failed with code {result.returncode}")
            
            self.log("✓ Patching complete!")
            
            # Step 3: Copy patcher.json to mod folder for client reference
            self.log("\n[3/4] Copying patcher.json for client reference...")
            patcher_json_dst = Path(self.output_path.get()) / "DreadRandovania" / "patcher.json"
            patcher_json_dst.parent.mkdir(parents=True, exist_ok=True)
            
            import shutil
            shutil.copy2(temp_patcher, patcher_json_dst)
            self.log(f"✓ Copied: {patcher_json_dst}")
            
            # Step 4: Copy randomizer_powerup.lua manually
            self.log("\n[4/5] Copying randomizer_powerup.lua...")
            randomizer_lua_src = Path(__file__).parent / "dread_scripts" / "randomizer_powerup.lua"
            randomizer_lua_dst = Path(self.output_path.get()) / "DreadRandovania" / "romfs" / "actors" / "items" / "randomizer_powerup" / "scripts" / "randomizer_powerup.lua"
            
            # Create directory if it doesn't exist
            randomizer_lua_dst.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy the file
            shutil.copy2(randomizer_lua_src, randomizer_lua_dst)
            self.log(f"✓ Copied: randomizer_powerup.lua")
            
            # Step 5: Verify output
            self.log("\n[5/5] Verifying output...")
            output_path = Path(self.output_path.get())
            
            # Check for key files
            romfs_path = output_path / "romfs"
            if romfs_path.exists():
                self.log(f"✓ Found: {romfs_path}")
                
                # Count patched files
                file_count = sum(1 for _ in romfs_path.rglob('*') if _.is_file())
                self.log(f"  Total files: {file_count}")
            else:
                self.log("⚠ Warning: romfs folder not found")
            
            # Success!
            self.log("\n" + "="*70)
            self.log("✅ SUCCESS! Patch applied successfully!")
            self.log("="*70)
            self.log("\nNext steps:")
            self.log("1. Launch Ryujinx")
            self.log("2. Start Metroid Bread")
            self.log("3. Start a new save file")
            self.log("4. Run MetroidBreadClient.py to connect")
            self.log("")
            
            # Clean up temp file
            if temp_patcher.exists():
                temp_patcher.unlink()
            
            self.root.after(0, lambda: self.set_status("✅ Patch Complete!", "green"))
            self.root.after(0, lambda: messagebox.showinfo("Success", 
                "Patch applied successfully!\n\nYou can now launch Metroid Bread in Ryujinx."))
            
        except Exception as e:
            error_msg = str(e)
            self.log(f"\n❌ ERROR: {error_msg}")
            self.log("\nPlease check:")
            self.log("- Spoiler file is valid")
            self.log("- Player name matches your YAML")
            self.log("- Base ROM folder contains romfs/system/files.toc")
            self.log("- open-dread-rando is installed (python3 -m pip install open-dread-rando)")
            
            self.root.after(0, lambda: self.set_status("❌ Error", "red"))
            self.root.after(0, lambda msg=error_msg: messagebox.showerror("Error", msg))
        
        finally:
            # Re-enable button
            self.root.after(0, lambda: self.patch_button.config(state='normal'))
            self.root.after(0, lambda: self.progress.stop())


def main():
    """Main entry point"""
    root = tk.Tk()
    
    # Set theme (if available)
    try:
        root.tk.call("source", "azure.tcl")
        root.tk.call("set_theme", "light")
    except:
        pass  # Theme not available, use default
    
    app = DreadPatcherGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
