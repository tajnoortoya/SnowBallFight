"""
Game State Management for Snowball Fight AI vs AI
Handles game state representation, actions, and game logic.

Freeze mechanic (fixed):
  When player A uses a freezeball on player B:
    - B becomes frozen for 2 turns
    - A immediately earns a BONUS TURN (pending_bonus_turn = A)
  During A's bonus turn, B has frozen >= 2 → 100% hit chance, B cannot dodge/act
  After A's bonus turn finishes, frozen counter ticks down normally:
    frozen=2 → skip B's turn → frozen=1 → B's next turn unfreezes them
  Net: A fires twice while B is helpless, B loses their next normal turn.
"""

import random
from enum import Enum
from typing import Tuple, List, Dict, Optional
import copy


class ActionType(Enum):
    MOVE_LEFT = 0
    MOVE_RIGHT = 1
    MOVE_FORWARD = 2
    MOVE_BACKWARD = 3
    AIM = 4
    THROW_SNOWBALL = 5
    USE_SPECIAL_ITEM = 6
    USE_FREEZEBALL = 7
    USE_MEDKIT = 8


class GameState:
    FIELD_WIDTH = 10
    FIELD_HEIGHT = 5
    INITIAL_HP = 100
    MAX_TURNS = 200
    HIT_DAMAGE = 20
    SNOWBALL_LIMIT = 20
    THROW_ACCURACY_BASE = 0.7
    MIN_DISTANCE = 1
    MAX_DISTANCE = 9
    MIN_THROW_FORCE = 0.5
    MAX_THROW_FORCE = 1.5

    def __init__(self):
        self.player1_pos = [self.FIELD_WIDTH // 2, self.FIELD_HEIGHT - 1]
        self.player2_pos = [self.FIELD_WIDTH // 2, 0]
        self.player1_home_row = self.FIELD_HEIGHT - 1
        self.player2_home_row = 0
        self.player1_prev_pos = self.player1_pos.copy()
        self.player2_prev_pos = self.player2_pos.copy()
        self.player1_hp = self.INITIAL_HP
        self.player2_hp = self.INITIAL_HP
        self.player1_snowballs = self.SNOWBALL_LIMIT
        self.player2_snowballs = self.SNOWBALL_LIMIT
        self.player1_items = {'freezeball': 1, 'medkit': 3}
        self.player2_items = {'freezeball': 1, 'medkit': 3}
        self.player1_frozen = 0
        self.player2_frozen = 0
        # Tracks which player has a pending bonus turn (after using freezeball)
        self.pending_bonus_turn: Optional[int] = None
        self.current_step = 0
        self.last_action_p1 = None
        self.last_action_p2 = None
        self.is_game_over = False
        self.winner = None
        self.current_player_turn = 1

    @property
    def current_turn(self):
        return self.SNOWBALL_LIMIT - min(self.player1_snowballs, self.player2_snowballs)

    def get_state_vector(self) -> Tuple:
        distance = abs(self.player1_pos[0] - self.player2_pos[0])
        return (
            tuple(self.player1_pos), tuple(self.player2_pos),
            self.player1_hp, self.player2_hp,
            self.player1_snowballs, self.player2_snowballs,
            distance, self.current_step,
            self.pending_bonus_turn,
        )

    def get_legal_actions(self, player: int) -> List[ActionType]:
        frozen_turns = self.player1_frozen if player == 1 else self.player2_frozen
        if frozen_turns > 0:
            return [ActionType.AIM]

        pos = self.player1_pos if player == 1 else self.player2_pos
        home_row = self.player1_home_row if player == 1 else self.player2_home_row
        snowballs = self.player1_snowballs if player == 1 else self.player2_snowballs
        items = self.player1_items if player == 1 else self.player2_items
        opp_frozen = self.player2_frozen if player == 1 else self.player1_frozen

        actions = []
        if snowballs > 0:
            actions.append(ActionType.THROW_SNOWBALL)
        if items.get('freezeball', 0) > 0 and opp_frozen == 0:
            actions.append(ActionType.USE_FREEZEBALL)
        if items.get('medkit', 0) > 0:
            actions.append(ActionType.USE_MEDKIT)
        actions.append(ActionType.AIM)
        if pos[0] > 0:
            actions.append(ActionType.MOVE_LEFT)
        if pos[0] < self.FIELD_WIDTH - 1:
            actions.append(ActionType.MOVE_RIGHT)
        if pos[1] > 0 and pos[1] - 1 >= home_row - 1:
            actions.append(ActionType.MOVE_BACKWARD)
        if pos[1] < self.FIELD_HEIGHT - 1 and pos[1] + 1 <= home_row + 1:
            actions.append(ActionType.MOVE_FORWARD)

        return actions if actions else [ActionType.AIM]

    def calculate_distance(self, player: int) -> float:
        pos = self.player1_pos if player == 1 else self.player2_pos
        opp = self.player2_pos if player == 1 else self.player1_pos
        dx = abs(pos[0] - opp[0])
        dy = abs(pos[1] - opp[1])
        return (dx**2 + dy**2) ** 0.5

    def calculate_throw_force(self, distance: float) -> float:
        if distance <= self.MIN_DISTANCE:
            return self.MIN_THROW_FORCE
        if distance >= self.MAX_DISTANCE:
            return self.MAX_THROW_FORCE
        return self.MIN_THROW_FORCE + (self.MAX_THROW_FORCE - self.MIN_THROW_FORCE) * \
               (distance - self.MIN_DISTANCE) / (self.MAX_DISTANCE - self.MIN_DISTANCE)

    def did_opponent_move_away(self, player: int) -> bool:
        curr = self.player2_pos if player == 1 else self.player1_pos
        prev = self.player2_prev_pos if player == 1 else self.player1_prev_pos
        return curr[0] != prev[0]

    def calculate_hit_chance(self, player: int, distance: float) -> float:
        opp_frozen = self.player2_frozen if player == 1 else self.player1_frozen
        if opp_frozen > 0:
            return 1.0  # Frozen = guaranteed hit

        if distance <= 4.0:
            base_accuracy = 0.85
        elif distance <= 6.0:
            base_accuracy = 0.70
        else:
            base_accuracy = 0.50

        dodge_bonus = 0.0
        if self.did_opponent_move_away(player):
            dodge_bonus = 0.35 if distance <= 4.0 else (0.40 if distance <= 6.0 else 0.45)
        else:
            opp_last = self.last_action_p2 if player == 1 else self.last_action_p1
            dodge_moves = {ActionType.MOVE_LEFT, ActionType.MOVE_RIGHT,
                           ActionType.MOVE_FORWARD, ActionType.MOVE_BACKWARD}
            if opp_last in dodge_moves:
                dodge_bonus = 0.10 if distance <= 4.0 else (0.15 if distance <= 6.0 else 0.20)

        return max(0.05, min(0.95, base_accuracy - dodge_bonus))

    def apply_action(self, player: int, action: ActionType) -> Dict:
        result = {'success': True, 'damage': 0, 'message': ''}
        pos = self.player1_pos if player == 1 else self.player2_pos
        home_row = self.player1_home_row if player == 1 else self.player2_home_row

        frozen_turns = self.player1_frozen if player == 1 else self.player2_frozen
        if frozen_turns > 0 and action != ActionType.AIM:
            result['success'] = False
            result['message'] = f"Player {player} is FROZEN! Can only AIM."
            return result

        if action == ActionType.MOVE_LEFT:
            if pos[0] > 0:
                pos[0] -= 1
                result['message'] = f"Player {player} shifted LEFT"
                result['is_dodge_movement'] = True
            else:
                result['success'] = False
                result['message'] = f"Player {player} can't move left (at edge)"

        elif action == ActionType.MOVE_RIGHT:
            if pos[0] < self.FIELD_WIDTH - 1:
                pos[0] += 1
                result['message'] = f"Player {player} shifted RIGHT"
                result['is_dodge_movement'] = True
            else:
                result['success'] = False
                result['message'] = f"Player {player} can't move right (at edge)"

        elif action == ActionType.MOVE_FORWARD:
            if pos[1] < self.FIELD_HEIGHT - 1 and pos[1] + 1 <= home_row + 1:
                pos[1] += 1
                result['message'] = f"Player {player} moved FORWARD"
                result['is_dodge_movement'] = True
            else:
                result['success'] = False
                result['message'] = f"Player {player} can't move forward"

        elif action == ActionType.MOVE_BACKWARD:
            if pos[1] > 0 and pos[1] - 1 >= home_row - 1:
                pos[1] -= 1
                result['message'] = f"Player {player} moved BACKWARD"
                result['is_dodge_movement'] = True
            else:
                result['success'] = False
                result['message'] = f"Player {player} can't move backward"

        elif action == ActionType.AIM:
            result['message'] = f"Player {player} aimed/waited"

        elif action == ActionType.THROW_SNOWBALL:
            snowballs = self.player1_snowballs if player == 1 else self.player2_snowballs
            if snowballs > 0:
                if player == 1:
                    self.player1_snowballs -= 1
                else:
                    self.player2_snowballs -= 1

                distance = self.calculate_distance(player)
                throw_force = self.calculate_throw_force(distance)
                hit_chance = self.calculate_hit_chance(player, distance)

                our_pos = self.player1_pos if player == 1 else self.player2_pos
                opp_pos = self.player2_pos if player == 1 else self.player1_pos
                dx = opp_pos[0] - our_pos[0]
                aim_dir = "STRAIGHT" if dx == 0 else ("DIAG-RIGHT" if dx > 0 else "DIAG-LEFT")
                result['aim_direction'] = aim_dir
                dist_str = f"{distance:.1f}"

                if random.random() < hit_chance:
                    opp_name = 2 if player == 1 else 1
                    if player == 1:
                        self.player2_hp -= self.HIT_DAMAGE
                    else:
                        self.player1_hp -= self.HIT_DAMAGE
                    result['damage'] = self.HIT_DAMAGE
                    result['distance'] = distance
                    result['throw_force'] = throw_force
                    result['hit'] = True
                    result['message'] = (f"P{player} aimed {aim_dir}, threw {dist_str}! "
                                         f"P{opp_name} HIT! -{self.HIT_DAMAGE} HP")
                else:
                    opp_name = 2 if player == 1 else 1
                    result['distance'] = distance
                    result['throw_force'] = throw_force
                    result['hit'] = False
                    if self.did_opponent_move_away(player):
                        opp_pos2 = self.player2_pos if player == 1 else self.player1_pos
                        opp_prev = self.player2_prev_pos if player == 1 else self.player1_prev_pos
                        dodge_dir = "LEFT" if opp_pos2[0] < opp_prev[0] else "RIGHT"
                        result['message'] = (f"P{player} aimed {aim_dir}, threw {dist_str}! "
                                             f"P{opp_name} dodged {dodge_dir}!")
                        result['dodge_type'] = 'positional'
                    else:
                        result['message'] = (f"P{player} aimed {aim_dir}, threw {dist_str}! "
                                             f"P{opp_name} dodged it!")
                        result['dodge_type'] = 'passive'
            else:
                result['success'] = False
                result['message'] = f"Player {player} has no snowballs left!"

        elif action == ActionType.USE_FREEZEBALL:
            items = self.player1_items if player == 1 else self.player2_items
            opp_frozen = self.player2_frozen if player == 1 else self.player1_frozen
            if items.get('freezeball', 0) > 0 and opp_frozen == 0:
                items['freezeball'] -= 1
                if player == 1:
                    self.player2_frozen = 2
                else:
                    self.player1_frozen = 2
                # Grant attacker immediate bonus turn
                self.pending_bonus_turn = player
                opp = 2 if player == 1 else 1
                result['message'] = (f"P{player} used Freezeball! "
                                     f"P{opp} FROZEN! P{player} gets BONUS TURN!")
                result['freeze_applied'] = True
                result['bonus_turn_granted'] = True
                result['item_used'] = 'freezeball'
            else:
                result['success'] = False
                result['message'] = f"Player {player} has no freezeball or opponent already frozen!"

        elif action == ActionType.USE_MEDKIT:
            items = self.player1_items if player == 1 else self.player2_items
            if items.get('medkit', 0) > 0:
                items['medkit'] -= 1
                if player == 1:
                    old_hp = self.player1_hp
                    self.player1_hp = min(self.player1_hp + 30, self.INITIAL_HP)
                    healed = self.player1_hp - old_hp
                else:
                    old_hp = self.player2_hp
                    self.player2_hp = min(self.player2_hp + 30, self.INITIAL_HP)
                    healed = self.player2_hp - old_hp
                result['message'] = f"P{player} used MedKit! Healed +{healed} HP"
                result['heal_amount'] = healed
                result['item_used'] = 'medkit'
            else:
                result['success'] = False
                result['message'] = f"Player {player} has no medkit!"

        elif action == ActionType.USE_SPECIAL_ITEM:
            items = self.player1_items if player == 1 else self.player2_items
            opp_frozen = self.player2_frozen if player == 1 else self.player1_frozen
            if items.get('freezeball', 0) > 0 and opp_frozen == 0:
                result = self.apply_action(player, ActionType.USE_FREEZEBALL)
            elif items.get('medkit', 0) > 0:
                result = self.apply_action(player, ActionType.USE_MEDKIT)
            else:
                result['success'] = False
                result['message'] = f"Player {player} has no items to use"

        if player == 1:
            self.last_action_p1 = action
        else:
            self.last_action_p2 = action

        return result

    def consume_bonus_turn(self, player: int) -> bool:
        """
        Returns True (and clears the flag) if player has a pending bonus turn.
        Call this at the start of a player's bonus turn phase.
        """
        if self.pending_bonus_turn == player:
            self.pending_bonus_turn = None
            return True
        return False

    def tick_frozen(self, player: int):
        """Decrement frozen counter when a player's turn is skipped."""
        if player == 1 and self.player1_frozen > 0:
            self.player1_frozen -= 1
        elif player == 2 and self.player2_frozen > 0:
            self.player2_frozen -= 1

    def check_game_over(self) -> bool:
        if self.player1_hp <= 0:
            self.is_game_over = True
            self.winner = 2
            return True
        if self.player2_hp <= 0:
            self.is_game_over = True
            self.winner = 1
            return True
        if self.current_step >= self.MAX_TURNS:
            self.is_game_over = True
            if self.player1_hp > self.player2_hp:
                self.winner = 1
            elif self.player2_hp > self.player1_hp:
                self.winner = 2
            else:
                self.winner = 0
            return True
        if self.player1_snowballs <= 0 and self.player2_snowballs <= 0:
            self.is_game_over = True
            if self.player1_hp > self.player2_hp:
                self.winner = 1
            elif self.player2_hp > self.player1_hp:
                self.winner = 2
            else:
                self.winner = 0
            return True
        return False

    def advance_step(self):
        self.current_step += 1

    def advance_turn(self):
        self.player1_prev_pos = self.player1_pos.copy()
        self.player2_prev_pos = self.player2_pos.copy()
        self.advance_step()

    def switch_turn(self):
        self.current_player_turn = 2 if self.current_player_turn == 1 else 1

    def get_current_player(self) -> int:
        return self.current_player_turn

    def copy(self):
        return copy.deepcopy(self)

    def __str__(self) -> str:
        bonus = f" [BONUS→P{self.pending_bonus_turn}]" if self.pending_bonus_turn else ""
        return (
            f"Turn {self.current_turn} (Step {self.current_step}){bonus}\n"
            f"P1: pos={self.player1_pos}, HP={self.player1_hp}, "
            f"snowballs={self.player1_snowballs}, items={self.player1_items}, "
            f"frozen={self.player1_frozen}\n"
            f"P2: pos={self.player2_pos}, HP={self.player2_hp}, "
            f"snowballs={self.player2_snowballs}, items={self.player2_items}, "
            f"frozen={self.player2_frozen}\n"
            f"Game Over: {self.is_game_over}, Winner: {self.winner}"
        )