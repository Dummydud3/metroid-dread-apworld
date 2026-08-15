#!/usr/bin/env python3
"""
Metroid Dread Archipelago - Seed Manager GUI

A simple GUI for:
1. Creating/editing YAML configuration files
2. Generating seeds and exporting .rdvgame files
3. Managing player settings and tricks

Requires Python 3.10+
"""

import sys

# Ensure Python 3
if sys.version_info < (3, 10):
    print("ERROR: Python 3.10 or newer is required!")
    print(f"You are running Python {sys.version_info.major}.{sys.version_info.minor}")
    print("\nPlease upgrade Python and try again.")
    sys.exit(1)

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import json
import os
import subprocess
import threading
import shutil
import time
from pathlib import Path
from typing import Dict, Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from worlds.metroid_dread.rdvgame_export import extract_from_ap_output
except ImportError:
    print("Warning: Could not import rdvgame_export")


def find_python_311() -> Optional[str]:
    """
    Find Python 3.11+ executable for running Generate.py
    
    Generate.py requires Python 3.11+, but the GUI can run on 3.10+.
    This function tries to locate a suitable Python 3.11+ interpreter.
    
    Returns:
        Path to Python 3.11+ executable, or None if not found
    """
    # Candidates to try (in order of preference)
    candidates = []
    
    # On Windows, try py launcher with specific versions
    if sys.platform == "win32":
        for minor in range(13, 10, -1):  # Try 3.13, 3.12, 3.11
            candidates.append(["py", f"-3.{minor}"])
        candidates.append(["py", "-3"])
    
    # Try explicit version commands
    for minor in range(13, 10, -1):
        candidates.append([f"python3.{minor}"])
    
    # Try generic commands
    candidates.append(["python3"])
    candidates.append(["python"])
    
    # Test each candidate
    for cmd_list in candidates:
        try:
            result = subprocess.run(
                cmd_list + ["--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                version_str = result.stdout or result.stderr
                # Parse version (e.g., "Python 3.11.9")
                if "Python 3." in version_str:
                    version_part = version_str.split("Python 3.")[1].split()[0]
                    minor = int(version_part.split(".")[0])
                    
                    if minor >= 11:
                        # Return the command list
                        return cmd_list
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, IndexError):
            continue
    
    return None


class DreadSeedManager(tk.Tk):
    """Main GUI window for Metroid Dread seed management"""
    
    def __init__(self):
        super().__init__()
        
        # Find Python 3.11+ for Generate.py
        self.python_311_cmd = find_python_311()
        if not self.python_311_cmd:
            messagebox.showwarning(
                "Python 3.11+ Not Found",
                "Could not find Python 3.11 or newer.\n\n"
                "Generate.py requires Python 3.11+.\n"
                "The GUI will work, but seed generation will fail.\n\n"
                "Please install Python 3.11+ and ensure it's in your PATH.\n"
                "On Windows, use 'py -3.11' or install from python.org"
            )
            self.python_311_cmd = [sys.executable]  # Fallback
        
        self.title("Metroid Dread Archipelago - Seed Manager")
        self.geometry("900x700")
        self.resizable(True, True)
        
        # Find Archipelago root directory
        self.ap_root = Path(__file__).parent.parent.parent
        
        # Configuration storage
        self.settings = self.load_default_config()
        
        # Create UI
        self.create_menu()
        self.create_tabs()
        
        # Status bar
        python_version_info = " ".join(self.python_311_cmd) if len(self.python_311_cmd) > 1 else self.python_311_cmd[0]
        self.status_var = tk.StringVar(value=f"Ready | Generate.py will use: {python_version_info}")
        status_bar = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def create_menu(self):
        """Create menu bar"""
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Load YAML", command=self.load_yaml)
        file_menu.add_command(label="Save YAML", command=self.save_yaml)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
        help_menu.add_command(label="Documentation", command=self.show_docs)
    
    def create_tabs(self):
        """Create tabbed interface"""
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Tab 1: Basic Settings
        self.basic_tab = ttk.Frame(notebook)
        notebook.add(self.basic_tab, text="Basic Settings")
        self.create_basic_settings()
        
        # Tab 2: Tricks
        self.tricks_tab = ttk.Frame(notebook)
        notebook.add(self.tricks_tab, text="Tricks & Glitches")
        self.create_tricks_settings()
        
        # Tab 3: Item Pool
        self.items_tab = ttk.Frame(notebook)
        notebook.add(self.items_tab, text="Item Pool")
        self.create_item_settings()
        
        # Tab 4: Generate & Export
        self.generate_tab = ttk.Frame(notebook)
        notebook.add(self.generate_tab, text="Generate & Export")
        self.create_generate_tab()
    
    def create_basic_settings(self):
        """Create basic settings tab"""
        frame = ttk.Frame(self.basic_tab, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Player name
        row = 0
        ttk.Label(frame, text="Player Name:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.player_name_var = tk.StringVar(value=self.settings.get("name", "Player1"))
        ttk.Entry(frame, textvariable=self.player_name_var, width=30).grid(row=row, column=1, sticky=tk.W, pady=5)

        # Game Goal
        row += 1
        ttk.Label(frame, text="Game Goal:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.game_goal_var = tk.StringVar(
            value=self.settings.get("Metroid Dread", {}).get("game_goal", "defeat_raven_beak")
        )
        goal_combo = ttk.Combobox(frame, textvariable=self.game_goal_var, width=27, state="readonly")
        goal_combo["values"] = ("defeat_raven_beak", "one_hundred_percent", "all_bosses")
        goal_combo.grid(row=row, column=1, sticky=tk.W, pady=5)

        # Required Metroid DNA (gates Raven Beak; 0 = no DNA gate)
        row += 1
        ttk.Label(frame, text="Required Metroid DNA:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.required_dna_var = tk.IntVar(
            value=self.settings.get("Metroid Dread", {}).get("required_dna", 0)
        )
        ttk.Spinbox(frame, from_=0, to=12, textvariable=self.required_dna_var, width=10).grid(
            row=row, column=1, sticky=tk.W, pady=5
        )

        row += 1
        ttk.Label(frame, text="DNA Placement:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.dna_placement_var = tk.StringVar(
            value=self.settings.get("Metroid Dread", {}).get("dna_placement", "prefer_emmi")
        )
        dna_place = ttk.Combobox(frame, textvariable=self.dna_placement_var, width=27, state="readonly")
        dna_place["values"] = ("prefer_emmi", "prefer_bosses", "anywhere")
        dna_place.grid(row=row, column=1, sticky=tk.W, pady=5)

        row += 1
        ttk.Label(frame, text="Door Lock Rando:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.door_lock_var = tk.StringVar(
            value=self.settings.get("Metroid Dread", {}).get("door_lock_rando", "vanilla")
        )
        door_combo = ttk.Combobox(frame, textvariable=self.door_lock_var, width=27, state="readonly")
        door_combo["values"] = ("vanilla", "individual_doors")
        door_combo.grid(row=row, column=1, sticky=tk.W, pady=5)

        row += 1
        ttk.Label(frame, text="Transport Rando:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.transport_var = tk.StringVar(
            value=self.settings.get("Metroid Dread", {}).get("transport_rando", "off")
        )
        transport_combo = ttk.Combobox(frame, textvariable=self.transport_var, width=27, state="readonly")
        transport_combo["values"] = ("off", "randomized")
        transport_combo.grid(row=row, column=1, sticky=tk.W, pady=5)

        # Progressive items section
        row += 1
        ttk.Separator(frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=10)
        
        row += 1
        ttk.Label(frame, text="Progressive Items:", font=("", 10, "bold")).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        self.progressive_vars = {}
        progressive_items = [
            ("progressive_beams", "Progressive Beams (Wide→Plasma→Wave)"),
            ("progressive_charge", "Progressive Charge Beam (Charge→Diffusion)"),
            ("progressive_missiles", "Progressive Missiles (Super→Ice)"),
            ("progressive_bombs", "Progressive Bombs (Bomb→Cross Bomb)"),
            ("progressive_suit", "Progressive Suit (Varia→Gravity)"),
            ("progressive_spin", "Progressive Spin (Spin→Space Jump)")
        ]
        
        for key, label in progressive_items:
            row += 1
            var = tk.BooleanVar(value=self.settings.get("Metroid Dread", {}).get(key, True))
            self.progressive_vars[key] = var
            ttk.Checkbutton(frame, text=label, variable=var).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        # Logic options
        row += 1
        ttk.Separator(frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=10)
        
        row += 1
        ttk.Label(frame, text="Logic Options:", font=("", 10, "bold")).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        row += 1
        self.early_morph_var = tk.BooleanVar(value=self.settings.get("Metroid Dread", {}).get("early_morph_ball", False))
        ttk.Checkbutton(frame, text="Early Morph Ball", variable=self.early_morph_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        row += 1
        ttk.Label(frame, text="Starting Location:").grid(row=row, column=0, sticky=tk.W, pady=2)
        start_val = self.settings.get("Metroid Dread", {}).get("starting_location", "default")
        if start_val is True or start_val == "true":
            start_val = "random_save_station"
        elif start_val is False or start_val == "false":
            start_val = "default"
        self.starting_location_var = tk.StringVar(value=str(start_val))
        start_combo = ttk.Combobox(
            frame,
            textvariable=self.starting_location_var,
            values=["default", "random_save_station"],
            width=28,
            state="readonly",
        )
        start_combo.grid(row=row, column=1, sticky=tk.W, pady=2)
        
        row += 1
        self.death_link_var = tk.BooleanVar(value=self.settings.get("Metroid Dread", {}).get("death_link", False))
        ttk.Checkbutton(frame, text="Death Link", variable=self.death_link_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=2)
    
    def create_tricks_settings(self):
        """Create tricks settings tab with scrollable area"""
        canvas = tk.Canvas(self.tricks_tab)
        scrollbar = ttk.Scrollbar(self.tricks_tab, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Tricks configuration
        self.trick_vars = {}
        
        # Labels / allowed levels match RDV long_name + used_trick_levels
        # (Disabled always available; Reverse Grapple Block is checkbox-only).
        tricks = [
            ("Basic Tricks", [
                ("knowledge_tricks", "Knowledge", ("disabled", "beginner", "intermediate", "advanced"), "Hidden object weaknesses"),
                ("movement_tricks", "Movement", ("disabled", "beginner", "intermediate", "advanced", "ludicrous"), "Precise jumps and niche movement"),
                ("combat_tricks", "Combat", ("disabled", "beginner", "intermediate", "advanced", "expert", "ludicrous"), "Fewer items / less health"),
                ("slide_jump", "Slide Jump", ("disabled", "beginner", "intermediate", "advanced"), "Jump further by sliding off cliffs"),
                ("wall_jump_tricks", "Wall Jump", ("disabled", "beginner", "intermediate", "advanced"), "Abuse wall jump movement"),
            ]),
            ("Advanced Movement", [
                ("infinite_bomb_jump", "Infinite Bomb Jump", ("disabled", "beginner", "intermediate", "advanced", "expert", "ludicrous"), "Chain bomb jumps to reach high places"),
                ("water_bomb_jump", "Water Bomb Jump", ("disabled", "beginner", "intermediate"), "Higher bomb jumps underwater"),
                ("water_space_jump", "Water Space Jump", ("disabled", "beginner", "intermediate", "advanced"), "Gain height underwater without Gravity"),
                ("single_wall_wall_jump", "Single-wall Wall Jump", ("disabled", "intermediate", "advanced", "expert"), "Climb a single wall"),
                ("diagonal_bomb_jump", "Diagonal Bomb Jump", ("disabled", "beginner", "intermediate", "advanced", "expert", "ludicrous"), "Diagonal momentum from bombs"),
                ("cross_bomb_launch", "Cross Bomb Launch", ("disabled", "beginner", "intermediate", "advanced"), "Horizontal momentum from Cross Bombs"),
                ("grapple_movement", "Grapple Movement", ("disabled", "beginner", "intermediate", "advanced"), "Use grapple without Spider Magnet"),
            ]),
            ("Speed Booster", [
                ("speedbooster_conservation", "Speed Booster Conservation", ("disabled", "beginner", "intermediate", "advanced", "expert"), "Maintain boost through complex areas"),
                ("short_boost", "Short Boost", ("disabled", "intermediate", "expert"), "Charge boost in smaller areas"),
                ("flash_shift_skip", "Flash Shift Skip", ("disabled", "beginner", "intermediate"), "Bypass shutter platforms without Flash Shift"),
            ]),
            ("Environmental", [
                ("heat_cold_runs", "Heat/Cold Runs", ("disabled", "beginner", "intermediate", "advanced"), "Traverse heat/cold without a suit"),
                ("climb_sloped_tunnels", "Climb Sloped Tunnels", ("disabled", "beginner", "intermediate", "advanced", "expert"), "Ascend sloped tunnels"),
                ("climb_sloped_surfaces", "Climb Sloped Surfaces", ("disabled", "beginner", "intermediate", "advanced", "expert"), "Gain height on slopes"),
                ("floor_clip", "Floor Clip", ("disabled", "intermediate", "advanced", "expert"), "Clip through floors"),
                ("damage_boost", "Damage Boost", ("disabled", "beginner", "intermediate", "advanced"), "Use enemy knockback for momentum"),
            ]),
            ("Combat & Items", [
                ("pseudo_wave", "Pseudo-Wave Beam", ("disabled", "beginner", "intermediate", "advanced"), "Fire through walls without Wave Beam"),
                ("diffusion_abuse", "Diffusion Abuse", ("disabled", "beginner", "intermediate", "advanced", "ludicrous"), "Use Diffusion in unintended ways"),
                ("stand_on_frozen_enemy", "Stand on Frozen Enemy", ("disabled", "beginner", "intermediate", "advanced", "expert"), "Use frozen enemies as platforms"),
                ("cross_bomb_skip", "Cross Bomb Skip", ("disabled", "intermediate", "advanced", "expert"), "Skip crumble blocks without Cross Bomb"),
            ]),
            ("Expert", [
                ("ledge_warp", "Ledge Warp", ("disabled", "intermediate"), "Frame-perfect ledge warping"),
            ])
        ]
        
        # Reverse Grapple Block is a toggle (RDV only uses Beginner), not a difficulty dropdown
        self.reverse_grapple_var = tk.BooleanVar(value=self.settings.get("Metroid Dread", {}).get("reverse_grapple_block", False))
        
        row = 0
        for category, trick_list in tricks:
            ttk.Label(scrollable_frame, text=category, font=("", 10, "bold")).grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=(10, 5))
            row += 1
            
            for key, label, levels, tooltip in trick_list:
                ttk.Label(scrollable_frame, text=label + ":").grid(row=row, column=0, sticky=tk.W, padx=(20, 5), pady=2)
                
                raw = self.settings.get("Metroid Dread", {}).get(key, "disabled")
                if raw not in levels:
                    raw = "disabled"
                var = tk.StringVar(value=raw)
                self.trick_vars[key] = var
                
                combo = ttk.Combobox(scrollable_frame, textvariable=var, width=15, state="readonly")
                combo['values'] = levels
                combo.grid(row=row, column=1, sticky=tk.W, padx=5, pady=2)
                
                ttk.Label(scrollable_frame, text=tooltip, foreground="gray").grid(row=row, column=2, sticky=tk.W, padx=5, pady=2)
                row += 1
        
        # Reverse Grapple Block (checkbox Toggle → Beginner when on)
        ttk.Label(scrollable_frame, text="Toggle", font=("", 10, "bold")).grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=(10, 5))
        row += 1
        ttk.Checkbutton(scrollable_frame, text="Reverse Grapple Block", variable=self.reverse_grapple_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=(20, 5), pady=2)
    
    def create_item_settings(self):
        """Create item pool settings tab"""
        frame = ttk.Frame(self.items_tab, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="Item Pool Configuration", font=("", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=10)
        
        self.item_vars = {}
        items = [
            ("energy_tanks", "Energy Tanks:", 0, 12, 8),
            ("energy_parts", "Energy Parts:", 0, 20, 16),
            ("missile_tanks", "Missile Tanks:", 10, 50, 35),
            ("missile_plus_tanks", "Missile+ Tanks:", 0, 15, 10),
            ("power_bomb_tanks", "Power Bomb Tanks:", 0, 15, 12),
        ]
        
        row = 1
        for key, label, min_val, max_val, default in items:
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky=tk.W, pady=5)
            var = tk.IntVar(value=self.settings.get("Metroid Dread", {}).get(key, default))
            self.item_vars[key] = var
            
            spinbox = ttk.Spinbox(frame, from_=min_val, to=max_val, textvariable=var, width=15)
            spinbox.grid(row=row, column=1, sticky=tk.W, pady=5, padx=10)
            row += 1
        
        # Info text
        row += 1
        ttk.Separator(frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=10)
        row += 1
        
        info_text = """Item Pool Tips:
        
• Energy Tanks: Each gives 100 energy
• Energy Parts: 4 parts = 1 Energy Tank
• Missile Tanks: Each gives +2 missiles
• Missile+ Tanks: Each gives +10 missiles
• Power Bomb Tanks: Each gives +1 power bomb

Adjust these values to control how many upgrades
appear in your seed. Lower values = harder game."""
        
        ttk.Label(frame, text=info_text, justify=tk.LEFT, foreground="gray").grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
    
    def create_generate_tab(self):
        """Create generation and export tab"""
        frame = ttk.Frame(self.generate_tab, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Output directory selection
        row = 0
        ttk.Label(frame, text="Output Directory:", font=("", 10, "bold")).grid(row=row, column=0, sticky=tk.W, pady=5)
        
        row += 1
        output_frame = ttk.Frame(frame)
        output_frame.grid(row=row, column=0, sticky=tk.EW, pady=5)
        
        self.output_dir_var = tk.StringVar(value=str(self.ap_root / "output"))
        ttk.Entry(output_frame, textvariable=self.output_dir_var, width=50).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(output_frame, text="Browse...", command=self.browse_output_dir).pack(side=tk.LEFT)
        
        # Action buttons
        row += 1
        ttk.Separator(frame, orient=tk.HORIZONTAL).grid(row=row, column=0, sticky=tk.EW, pady=15)
        
        row += 1
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=row, column=0, pady=10)
        
        ttk.Button(button_frame, text="Save YAML Only", command=self.save_yaml_only, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Generate Seed", command=self.generate_seed, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Generate + Export .rdvgame", command=self.generate_and_export, width=25).pack(side=tk.LEFT, padx=5)
        
        # Progress log
        row += 1
        ttk.Label(frame, text="Output Log:", font=("", 10, "bold")).grid(row=row, column=0, sticky=tk.W, pady=(10, 5))
        
        row += 1
        self.log_text = scrolledtext.ScrolledText(frame, width=80, height=15, state='disabled')
        self.log_text.grid(row=row, column=0, sticky=tk.NSEW, pady=5)
        
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(row, weight=1)
    
    def log_message(self, message: str):
        """Add message to log"""
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.update_idletasks()
    
    def load_default_config(self) -> Dict[str, Any]:
        """Load default configuration"""
        return {
            "name": "Player1",
            "game": "Metroid Dread",
            "Metroid Dread": {
                "game_goal": "defeat_raven_beak",
                "required_dna": 0,
                "dna_placement": "prefer_emmi",
                "door_lock_rando": "vanilla",
                "transport_rando": "off",
                "energy_tanks": 8,
                "energy_parts": 16,
                "missile_tanks": 35,
                "missile_plus_tanks": 10,
                "power_bomb_tanks": 12,
                "progressive_beams": True,
                "progressive_charge": True,
                "progressive_missiles": False,
                "progressive_bombs": True,
                "progressive_suit": True,
                "progressive_spin": True,
                "starting_location": "default",
                "early_morph_ball": False,
                "death_link": False,
            }
        }
    
    def get_current_config(self) -> Dict[str, Any]:
        """Get current configuration from UI"""
        config = {
            "name": self.player_name_var.get(),
            "game": "Metroid Dread",
            "Metroid Dread": {
                "game_goal": self.game_goal_var.get(),
                "required_dna": self.required_dna_var.get(),
                "dna_placement": self.dna_placement_var.get(),
                "door_lock_rando": self.door_lock_var.get(),
                "transport_rando": self.transport_var.get(),
                "early_morph_ball": self.early_morph_var.get(),
                "starting_location": self.starting_location_var.get(),
                "death_link": self.death_link_var.get(),
            }
        }
        
        # Add progressive items
        for key, var in self.progressive_vars.items():
            config["Metroid Dread"][key] = var.get()
        
        # Add item pool
        for key, var in self.item_vars.items():
            config["Metroid Dread"][key] = var.get()
        
        # Add tricks
        for key, var in self.trick_vars.items():
            config["Metroid Dread"][key] = var.get()
        
        config["Metroid Dread"]["reverse_grapple_block"] = self.reverse_grapple_var.get()
        
        return config
    
    def browse_output_dir(self):
        """Browse for output directory"""
        directory = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if directory:
            self.output_dir_var.set(directory)
    
    def load_yaml(self):
        """Load YAML file"""
        filename = filedialog.askopenfilename(
            title="Load YAML Configuration",
            filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")]
        )
        if filename:
            try:
                import yaml
                with open(filename, 'r') as f:
                    loaded_config = yaml.safe_load(f)
                self.settings = loaded_config
                self.load_config_to_ui()
                self.status_var.set(f"Loaded: {filename}")
                messagebox.showinfo("Success", "Configuration loaded successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load YAML:\n{str(e)}")
    
    def load_config_to_ui(self):
        """Load configuration into UI elements"""
        # Update all UI elements with settings values
        self.player_name_var.set(self.settings.get("name", "Player1"))
        
        dread_config = self.settings.get("Metroid Dread", {})
        goal = dread_config.get("game_goal", "defeat_raven_beak")
        if goal == "dna_hunt":
            goal = "defeat_raven_beak"
        self.game_goal_var.set(goal)
        self.required_dna_var.set(dread_config.get("required_dna", 0))
        self.dna_placement_var.set(dread_config.get("dna_placement", "prefer_emmi"))
        self.door_lock_var.set(dread_config.get("door_lock_rando", "vanilla"))
        self.transport_var.set(dread_config.get("transport_rando", "off"))
        
        # Progressive items
        for key, var in self.progressive_vars.items():
            var.set(dread_config.get(key, True))
        
        # Item pool
        for key, var in self.item_vars.items():
            if key in dread_config:
                var.set(dread_config[key])
        
        # Tricks
        for key, var in self.trick_vars.items():
            var.set(dread_config.get(key, "disabled"))
        
        self.reverse_grapple_var.set(dread_config.get("reverse_grapple_block", False))
        self.early_morph_var.set(dread_config.get("early_morph_ball", False))
        start_val = dread_config.get("starting_location", "default")
        if dread_config.get("randomize_starting_location"):
            start_val = "random_save_station"
        elif start_val is True:
            start_val = "random_save_station"
        elif start_val is False:
            start_val = "default"
        self.starting_location_var.set(str(start_val))
        self.death_link_var.set(dread_config.get("death_link", False))
    
    def save_yaml(self):
        """Save YAML file"""
        filename = filedialog.asksaveasfilename(
            title="Save YAML Configuration",
            defaultextension=".yaml",
            filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")]
        )
        if filename:
            self.save_yaml_to_file(filename)
    
    def save_yaml_only(self):
        """Save YAML without generating"""
        output_dir = Path(self.output_dir_var.get())
        output_dir.mkdir(parents=True, exist_ok=True)
        
        player_name = self.player_name_var.get()
        filename = output_dir / f"{player_name}_dread.yaml"
        
        self.save_yaml_to_file(str(filename))
    
    def save_yaml_to_file(self, filename: str):
        """Save configuration to YAML file"""
        try:
            import yaml
            config = self.get_current_config()
            
            with open(filename, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            
            self.status_var.set(f"Saved: {filename}")
            self.log_message(f"✓ Saved YAML to: {filename}")
            messagebox.showinfo("Success", f"Configuration saved to:\n{filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save YAML:\n{str(e)}")
    
    def generate_seed(self):
        """Generate Archipelago seed"""
        # Create a clean subdirectory for this generation to avoid conflicts with old .zip files
        timestamp = int(time.time())
        
        base_output_dir = Path(self.output_dir_var.get())
        output_dir = base_output_dir / f"dread_seed_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        player_name = self.player_name_var.get()
        yaml_file = output_dir / f"{player_name}_dread.yaml"
        
        try:
            import yaml
            config = self.get_current_config()
            
            with open(yaml_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            
            self.log_message(f"✓ Created YAML: {yaml_file}")
            
            # Run Generate.py
            self.log_message("\n" + "="*50)
            self.log_message("Generating Archipelago seed...")
            self.log_message("="*50)
            
            def run_generation():
                try:
                    generate_script = self.ap_root / "Generate.py"
                    cmd = self.python_311_cmd + [
                        str(generate_script),
                        "--player_files_path", str(output_dir),
                        "--outputpath", str(output_dir / "generated")
                    ]
                    
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        cwd=str(self.ap_root)
                    )
                    
                    for line in process.stdout:
                        self.log_message(line.rstrip())
                    
                    process.wait()
                    
                    if process.returncode == 0:
                        self.log_message("\n✓ Seed generated successfully!")
                        self.status_var.set("Generation complete")
                    else:
                        self.log_message(f"\n✗ Generation failed with code {process.returncode}")
                        self.status_var.set("Generation failed")
                        
                except Exception as e:
                    self.log_message(f"\n✗ Error: {str(e)}")
                    self.status_var.set("Generation error")
            
            # Run in thread to keep GUI responsive
            thread = threading.Thread(target=run_generation, daemon=True)
            thread.start()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate seed:\n{str(e)}")
    
    def generate_and_export(self):
        """Generate seed and export .rdvgame"""
        # Create a clean subdirectory for this generation to avoid conflicts with old .zip files
        timestamp = int(time.time())
        
        base_output_dir = Path(self.output_dir_var.get())
        output_dir = base_output_dir / f"dread_seed_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        player_name = self.player_name_var.get()
        yaml_file = output_dir / f"{player_name}_dread.yaml"
        
        try:
            import yaml
            config = self.get_current_config()
            
            with open(yaml_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            
            self.log_message(f"✓ Created YAML: {yaml_file}")
            
            # Run Generate.py then rdvgame export
            self.log_message("\n" + "="*50)
            self.log_message("Generating Archipelago seed...")
            self.log_message("="*50)
            
            def run_full_generation():
                try:
                    # Step 1: Generate seed
                    generate_script = self.ap_root / "Generate.py"
                    generated_dir = output_dir / "generated"
                    
                    cmd = self.python_311_cmd + [
                        str(generate_script),
                        "--player_files_path", str(output_dir),
                        "--outputpath", str(generated_dir)
                    ]
                    
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        cwd=str(self.ap_root)
                    )
                    
                    for line in process.stdout:
                        self.log_message(line.rstrip())
                    
                    process.wait()
                    
                    if process.returncode != 0:
                        self.log_message(f"\n✗ Generation failed with code {process.returncode}")
                        self.status_var.set("Generation failed")
                        return
                    
                    self.log_message("\n✓ Seed generated successfully!")
                    
                    # Step 2: Export .rdvgame
                    self.log_message("\n" + "="*50)
                    self.log_message("Exporting .rdvgame file...")
                    self.log_message("="*50)
                    
                    # Find the generated output
                    # Generate.py creates the files directly in generated_dir
                    # Look for the AP_.zip file
                    if not generated_dir.exists():
                        self.log_message("✗ Generated directory not found!")
                        self.status_var.set("Export failed")
                        return
                    
                    # List all files in generated_dir
                    all_files = list(generated_dir.iterdir())
                    self.log_message(f"Files in generated directory: {[f.name for f in all_files]}")
                    
                    # Look for the seed folder (AP_<number> directory) or use generated_dir itself
                    seed_folders = [f for f in all_files if f.is_dir() and f.name.startswith("AP_")]
                    
                    if seed_folders:
                        # Use the AP_* subfolder if it exists
                        seed_folder = seed_folders[0]
                        self.log_message(f"Using seed folder: {seed_folder}")
                    else:
                        # Use the generated_dir itself (single-player generation)
                        seed_folder = generated_dir
                        self.log_message(f"Using generated directory: {seed_folder}")
                    
                    # Run rdvgame export (can use current Python, doesn't need 3.11+)
                    rdvgame_script = self.ap_root / "worlds" / "metroid_dread" / "rdvgame_export.py"
                    cmd = [
                        sys.executable,
                        str(rdvgame_script),
                        str(seed_folder),
                        player_name
                    ]
                    
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True
                    )
                    
                    for line in process.stdout:
                        self.log_message(line.rstrip())
                    
                    process.wait()
                    
                    if process.returncode == 0:
                        self.log_message("\n✓ .rdvgame file created successfully!")
                        self.log_message(f"\nOutput location: {seed_folder}")
                        self.status_var.set("Complete! Ready to patch in Randovania")
                        
                        messagebox.showinfo(
                            "Success!",
                            f"Seed generated and .rdvgame exported!\n\n"
                            f"Location: {seed_folder}\n\n"
                            f"Next step: Open the .rdvgame file in Randovania to patch your game."
                        )
                    else:
                        self.log_message(f"\n✗ Export failed with code {process.returncode}")
                        self.status_var.set("Export failed")
                        
                except Exception as e:
                    self.log_message(f"\n✗ Error: {str(e)}")
                    self.status_var.set("Error")
            
            # Run in thread to keep GUI responsive
            thread = threading.Thread(target=run_full_generation, daemon=True)
            thread.start()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start generation:\n{str(e)}")
    
    def show_about(self):
        """Show about dialog"""
        messagebox.showinfo(
            "About",
            "Metroid Dread Archipelago - Seed Manager\n\n"
            "A GUI tool for creating YAML configurations and generating seeds\n"
            "for Metroid Dread multiworld randomizer.\n\n"
            "Features:\n"
            "• Configure all 26 tricks and glitches\n"
            "• Customize item pool\n"
            "• Generate seeds and export .rdvgame files\n\n"
            "Version 1.0.0"
        )
    
    def show_docs(self):
        """Show documentation"""
        docs_path = self.ap_root / "worlds" / "metroid_dread" / "CLIENT_GUIDE.md"
        if docs_path.exists():
            import webbrowser
            webbrowser.open(str(docs_path))
        else:
            messagebox.showinfo(
                "Documentation",
                "Documentation files:\n\n"
                "• CLIENT_GUIDE.md - Complete setup guide\n"
                "• ARCHITECTURE.md - Technical details\n"
                "• QUICK_REFERENCE.md - Quick reference\n\n"
                "Located in: worlds/metroid_dread/"
            )


def main():
    """Main entry point"""
    # Version check already done at module level
    
    try:
        # Check for required modules
        import yaml
    except ImportError:
        try:
            import tkinter.messagebox as mb
            mb.showerror(
                "Missing Dependency",
                "PyYAML is required. Install with:\n\npip install pyyaml"
            )
        except:
            print("ERROR: PyYAML is required. Install with: pip install pyyaml")
        return
    
    print(f"Starting Dread Seed Manager with Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    app = DreadSeedManager()
    app.mainloop()


if __name__ == "__main__":
    main()
