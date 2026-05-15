"""
Snowball Fight: AI vs AI Visual Game
Simultaneous gameplay with attack cooldowns
Run: python play.py
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import and run the GUI
from gui_fixed import CompleteGameGUI

if __name__ == "__main__":
    print("="*70)
    print("SNOWBALL FIGHT: AI vs AI Visual Game")
    print("Simultaneous gameplay with 2-second attack cooldown")
    print("="*70)
    gui = CompleteGameGUI()
    gui.run()
