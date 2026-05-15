"""
Main Game Logic - Simultaneous Gameplay
Both agents act at the same time each step.
Attack cooldown: 2 steps between attacks.
"""

from typing import Dict
from game_state import GameState, ActionType
from minimax_agent import MinimaxAgent
from mcts_agent import MCTSAgent
import time


class SnowballGame:
    def __init__(self, agent1_type: str = "minimax", agent2_type: str = "mcts"):
        self.state = GameState()
        self.agent1_type = agent1_type
        self.agent2_type = agent2_type

        self.agent1 = (MinimaxAgent(player_id=1, depth=3)
                       if agent1_type == "minimax"
                       else MCTSAgent(player_id=1, iterations=400))

        self.agent2 = (MinimaxAgent(player_id=2, depth=3)
                       if agent2_type == "minimax"
                       else MCTSAgent(player_id=2, iterations=400))

        self.game_log = []
        self.turn_history = []

    def play_turn(self) -> bool:
        """Play one step where both agents act simultaneously."""
        self.state.advance_turn()
        turn_num = self.state.current_turn

        print(f"\n{'='*60}")
        print(f"STEP {self.state.current_step} (Turn {turn_num})")
        print(self.state)

        print("\n--- Both agents act simultaneously ---")

        # Get actions from both agents
        start_p1 = time.time()
        action_p1 = self.agent1.get_best_action(self.state)
        t_p1 = time.time() - start_p1

        start_p2 = time.time()
        action_p2 = self.agent2.get_best_action(self.state)
        t_p2 = time.time() - start_p2

        # Apply both actions
        result_p1 = self.state.apply_action(1, action_p1)
        result_p2 = self.state.apply_action(2, action_p2)

        print(f"  P1: {action_p1.name:20s} -> {result_p1['message']}  ({t_p1:.3f}s)")
        print(f"  P2: {action_p2.name:20s} -> {result_p2['message']}  ({t_p2:.3f}s)")

        print(f"  HP: P1={self.state.player1_hp} | P2={self.state.player2_hp}")
        if self.state.player1_attack_cooldown > 0 or self.state.player2_attack_cooldown > 0:
            print(f"  Attack Cooldowns: P1={self.state.player1_attack_cooldown} | P2={self.state.player2_attack_cooldown}")

        # Track history
        self.turn_history.append({
            'turn': turn_num,
            'player': 1,
            'action': action_p1.name,
            'result': result_p1['message'],
            'p1_hp': self.state.player1_hp,
            'p2_hp': self.state.player2_hp,
            'time': t_p1,
        })
        self.turn_history.append({
            'turn': turn_num,
            'player': 2,
            'action': action_p2.name,
            'result': result_p2['message'],
            'p1_hp': self.state.player1_hp,
            'p2_hp': self.state.player2_hp,
            'time': t_p2,
        })

        # Check for game over
        return not self.state.check_game_over()

    def play_full_game(self) -> Dict:
        print(f"\n{'#'*60}")
        print(f"# {self.agent1_type.upper()} vs {self.agent2_type.upper()}")
        print(f"# Both agents act simultaneously")
        print(f"{'#'*60}\n")

        start = time.time()
        while self.play_turn():
            if self.state.current_step > 500:
                break
        game_time = time.time() - start

        print(f"\nGAME OVER -- Winner: {self.state.winner}")
        print(f"Steps: {self.state.current_step}  Time: {game_time:.2f}s")
        print(f"P1 HP: {self.state.player1_hp}  P2 HP: {self.state.player2_hp}")
        print(f"P1 Items: {self.state.player1_items}  P2 Items: {self.state.player2_items}")

        return {
            'winner':             self.state.winner,
            'steps':              self.state.current_step,
            'final_p1_hp':        self.state.player1_hp,
            'final_p2_hp':        self.state.player2_hp,
            'p1_items_remaining': self.state.player1_items.copy(),
            'p2_items_remaining': self.state.player2_items.copy(),
            'game_time':          game_time,
            'agent1_type':        self.agent1_type,
            'agent2_type':        self.agent2_type,
            'history':            self.turn_history,
        }

    def get_game_state(self) -> GameState:
        return self.state

    def get_history(self) -> list:
        return self.turn_history


if __name__ == "__main__":
    game = SnowballGame(agent1_type="minimax", agent2_type="mcts")
    results = game.play_full_game()