"""
Monte Carlo Tree Search (MCTS) AI Agent — Optimized Tactical v5

Key improvements:
  - Full bonus-turn simulation in rollout (freeze gives guaranteed extra throw)
  - Proactive dodge: predict opponent's throw and sidestep BEFORE it lands
  - Attack timing heuristic: throw after opponent moves (dodge advantage expires)
  - Better reward shaping for positional play and freeze exploitation
  - UCB-guided selection with proper adversarial backpropagation
"""

import random
import math
from typing import Optional, Dict
from game_state import GameState, ActionType


class MCTSNode:
    def __init__(self, state: GameState, parent: Optional['MCTSNode'] = None,
                 action: Optional[ActionType] = None, player_id: Optional[int] = None):
        self.state = state
        self.parent = parent
        self.action = action
        self.children: Dict[ActionType, 'MCTSNode'] = {}
        self.visits = 0
        self.value = 0.0
        self.player_id = player_id if parent is None else (2 if parent.player_id == 1 else 1)
        self.untried_actions = state.get_legal_actions(self.player_id)

    def ucb1(self, c: float = 1.41) -> float:
        if self.visits == 0:
            return float('inf')
        return self.value / self.visits + c * math.sqrt(math.log(self.parent.visits) / self.visits)

    def best_child(self, c: float = 1.41) -> 'MCTSNode':
        return max(self.children.values(), key=lambda ch: ch.ucb1(c))

    def select_untried_action(self) -> Optional[ActionType]:
        if not self.untried_actions:
            return None
        # Priority order for exploration
        for priority_action in [ActionType.USE_FREEZEBALL, ActionType.THROW_SNOWBALL]:
            if priority_action in self.untried_actions and random.random() < 0.7:
                self.untried_actions.remove(priority_action)
                return priority_action
        move_actions = [a for a in self.untried_actions
                        if a in {ActionType.MOVE_LEFT, ActionType.MOVE_RIGHT}]
        if move_actions and random.random() < 0.4:
            a = random.choice(move_actions)
            self.untried_actions.remove(a)
            return a
        a = self.untried_actions[0]
        self.untried_actions.remove(a)
        return a

    def is_fully_expanded(self) -> bool:
        return len(self.untried_actions) == 0


class MCTSAgent:
    def __init__(self, player_id: int, iterations: int = 500, exploration: float = 1.41):
        self.player_id = player_id
        self.opponent_id = 2 if player_id == 1 else 1
        self.iterations = iterations
        self.exploration = exploration
        self.nodes_explored = 0

    def _smart_action(self, state: GameState, player: int) -> ActionType:
        """
        Tactical rollout policy — returns a smart action for the given player.
        Implements: exploit frozen, heal critical, freeze+throw, proactive dodge, attack.
        """
        legal = state.get_legal_actions(player)
        if not legal:
            return ActionType.AIM

        snowballs = state.player1_snowballs if player == 1 else state.player2_snowballs
        hp = state.player1_hp if player == 1 else state.player2_hp
        items = state.player1_items if player == 1 else state.player2_items
        opp_frozen = state.player2_frozen if player == 1 else state.player1_frozen
        opp_balls = state.player2_snowballs if player == 1 else state.player1_snowballs
        our_pos = state.player1_pos if player == 1 else state.player2_pos
        opp_pos = state.player2_pos if player == 1 else state.player1_pos
        opp_last = state.last_action_p2 if player == 1 else state.last_action_p1
        hp_lost = GameState.INITIAL_HP - hp
        h_dist = abs(our_pos[0] - opp_pos[0])
        distance = state.calculate_distance(player)
        dodge_moves = {ActionType.MOVE_LEFT, ActionType.MOVE_RIGHT,
                       ActionType.MOVE_FORWARD, ActionType.MOVE_BACKWARD}

        # 1. Exploit frozen opponent — guaranteed hit
        if opp_frozen > 0 and snowballs > 0 and ActionType.THROW_SNOWBALL in legal:
            return ActionType.THROW_SNOWBALL

        # 2. Critical heal
        if (hp <= 35 and hp_lost >= 25
                and items.get('medkit', 0) > 0
                and ActionType.USE_MEDKIT in legal
                and random.random() < 0.90):
            return ActionType.USE_MEDKIT

        # 3. Freeze + guaranteed bonus throw
        if (items.get('freezeball', 0) > 0 and opp_frozen == 0
                and snowballs >= 2 and hp_lost > 0
                and ActionType.USE_FREEZEBALL in legal
                and random.random() < 0.80):
            return ActionType.USE_FREEZEBALL

        # 4. Proactive dodge: sidestep when in opponent's line of fire
        if (opp_balls > 0 and opp_frozen == 0
                and h_dist == 0  # same column = easy target
                and snowballs == 0  # no ammo to attack back
                and random.random() < 0.85):
            mv = [a for a in legal if a in dodge_moves]
            if mv:
                # Prefer moving toward centre
                centre = GameState.FIELD_WIDTH // 2
                best = min(mv, key=lambda a: abs(
                    (our_pos[0] - 1 if a == ActionType.MOVE_LEFT else
                     our_pos[0] + 1 if a == ActionType.MOVE_RIGHT else our_pos[0]) - centre))
                return best

        # 5. Attack timing: throw immediately after opponent moved (dodge expires)
        if (opp_last in dodge_moves and snowballs > 0
                and ActionType.THROW_SNOWBALL in legal
                and distance <= 7.0
                and random.random() < 0.70):
            return ActionType.THROW_SNOWBALL

        # 6. Normal throw (weighted by range)
        if snowballs > 0 and ActionType.THROW_SNOWBALL in legal:
            # Throw probability scales with hit chance at current distance
            hit_ch = state.calculate_hit_chance(player, distance)
            if random.random() < hit_ch * 0.90:
                return ActionType.THROW_SNOWBALL
            # Maybe dodge first to improve future throw
            if opp_balls > 0 and h_dist == 0 and random.random() < 0.55:
                mv = [a for a in legal if a in dodge_moves]
                if mv:
                    return random.choice(mv)
            return ActionType.THROW_SNOWBALL

        # 7. No ammo: dodge if threatened
        if snowballs == 0 and opp_balls > 0:
            mv = [a for a in legal if a in dodge_moves]
            if mv and random.random() < 0.65:
                return random.choice(mv)

        # 8. Heal when moderately hurt and safe
        if (hp_lost >= 30 and items.get('medkit', 0) > 0
                and ActionType.USE_MEDKIT in legal
                and random.random() < 0.50):
            return ActionType.USE_MEDKIT

        return random.choice(legal)

    def simulate(self, state: GameState) -> float:
        """
        Smart rollout to terminal or max depth.
        Returns reward from OUR (self.player_id) perspective.
        """
        sim = state.copy()
        max_steps = 40
        steps = 0
        current_player = self.player_id  # start from our perspective

        while not sim.is_game_over and steps < max_steps:
            # Handle frozen turn skip
            frozen = sim.player1_frozen if current_player == 1 else sim.player2_frozen
            if frozen > 0:
                sim.tick_frozen(current_player)
                sim.advance_step()
                current_player = 2 if current_player == 1 else 1
                steps += 1
                continue

            action = self._smart_action(sim, current_player)
            result = sim.apply_action(current_player, action)
            sim.check_game_over()

            # Handle bonus turn in simulation
            if result.get('bonus_turn_granted') and sim.pending_bonus_turn == current_player:
                sim.consume_bonus_turn(current_player)
                if not sim.is_game_over:
                    bonus_action = self._smart_action(sim, current_player)
                    sim.apply_action(current_player, bonus_action)
                    sim.check_game_over()

            sim.advance_turn()
            current_player = 2 if current_player == 1 else 1
            steps += 1

        # Score final state
        if self.player_id == 1:
            our_hp, opp_hp = sim.player1_hp, sim.player2_hp
            opp_frozen = sim.player2_frozen
            our_pos, opp_pos = sim.player1_pos, sim.player2_pos
            our_balls = sim.player1_snowballs
        else:
            our_hp, opp_hp = sim.player2_hp, sim.player1_hp
            opp_frozen = sim.player1_frozen
            our_pos, opp_pos = sim.player2_pos, sim.player1_pos
            our_balls = sim.player2_snowballs

        if sim.is_game_over:
            if sim.winner == self.player_id:
                reward = 1.0 + our_hp / GameState.INITIAL_HP * 0.5
            elif sim.winner == self.opponent_id:
                reward = -1.0 - opp_hp / GameState.INITIAL_HP * 0.5
            else:
                reward = 0.1  # draw is slightly better than losing
        else:
            reward = (our_hp - opp_hp) / GameState.INITIAL_HP

        # Positional bonuses
        h_dist = abs(our_pos[0] - opp_pos[0])
        if opp_frozen > 0:
            reward += 0.30  # bonus turn advantage
        if h_dist >= 1 and h_dist <= 3:
            reward += 0.04  # good dodge positioning
        elif h_dist == 0:
            reward -= 0.06  # in the line of fire

        return reward

    def backpropagate(self, node: MCTSNode, reward: float):
        while node is not None:
            node.visits += 1

            # The root node has no parent, just track the baseline reward
            if node.parent is None:
                node.value += reward
            # If the action that led to this node was made by US, we want a HIGH value for winning
            elif node.parent.player_id == self.player_id:
                node.value += reward
            # If the action that led here was made by the OPPONENT, they want a HIGH value for beating us
            else:
                node.value -= reward

            node = node.parent

    def tree_policy(self, node: MCTSNode) -> MCTSNode:
        while not node.state.is_game_over:
            if not node.is_fully_expanded():
                return node
            node = node.best_child(self.exploration)
        return node

    def search(self, state: GameState) -> MCTSNode:
        root = MCTSNode(state, player_id=self.player_id)
        self.nodes_explored = 0

        for _ in range(self.iterations):
            # SELECT
            leaf = self.tree_policy(root)
            self.nodes_explored += 1

            # EXPAND
            if not leaf.state.is_game_over:
                action = leaf.select_untried_action()
                if action:
                    new_state = leaf.state.copy()
                    result = new_state.apply_action(leaf.player_id, action)
                    # Simulate bonus turn in tree expansion
                    if result.get('bonus_turn_granted') and new_state.pending_bonus_turn == leaf.player_id:
                        new_state.consume_bonus_turn(leaf.player_id)
                        bonus_legal = new_state.get_legal_actions(leaf.player_id)
                        bonus_a = (ActionType.THROW_SNOWBALL
                                   if ActionType.THROW_SNOWBALL in bonus_legal
                                   else bonus_legal[0])
                        new_state.apply_action(leaf.player_id, bonus_a)
                    new_state.check_game_over()
                    new_state.advance_turn()
                    child = MCTSNode(new_state, leaf, action)
                    leaf.children[action] = child
                    leaf = child

            # SIMULATE
            reward = self.simulate(leaf.state)

            # BACKPROPAGATE
            self.backpropagate(leaf, reward)

        return root

    def get_best_action(self, state: GameState) -> ActionType:
        our_hp    = state.player1_hp if self.player_id == 1 else state.player2_hp
        opp_hp    = state.player1_hp if self.player_id == 2 else state.player2_hp
        our_balls = state.player1_snowballs if self.player_id == 1 else state.player2_snowballs
        opp_balls = state.player2_snowballs if self.player_id == 1 else state.player1_snowballs
        our_items = state.player1_items if self.player_id == 1 else state.player2_items
        opp_frozen = state.player2_frozen if self.player_id == 1 else state.player1_frozen
        our_pos   = state.player1_pos if self.player_id == 1 else state.player2_pos
        opp_pos   = state.player2_pos if self.player_id == 1 else state.player1_pos
        our_last  = state.last_action_p1 if self.player_id == 1 else state.last_action_p2
        opp_last  = state.last_action_p2 if self.player_id == 1 else state.last_action_p1

        legal = state.get_legal_actions(self.player_id)
        our_hp_lost = GameState.INITIAL_HP - our_hp
        opp_hp_lost = GameState.INITIAL_HP - opp_hp
        h_dist = abs(our_pos[0] - opp_pos[0])
        distance = state.calculate_distance(self.player_id)
        dodge_moves = {ActionType.MOVE_LEFT, ActionType.MOVE_RIGHT,
                       ActionType.MOVE_FORWARD, ActionType.MOVE_BACKWARD}
        combat_started = (our_hp_lost > 0 or opp_hp_lost > 0
                          or our_balls < GameState.SNOWBALL_LIMIT
                          or opp_balls < GameState.SNOWBALL_LIMIT)

        # ── Hard overrides ────────────────────────────────────────

        # 1. Exploit frozen opponent immediately
        if opp_frozen > 0 and our_balls > 0 and ActionType.THROW_SNOWBALL in legal:
            print(f"[MCTS-P{self.player_id}] Opponent FROZEN — guaranteed throw!")
            return ActionType.THROW_SNOWBALL

        # 2. Critical heal
        if (our_hp <= 40 and our_hp_lost >= 25
                and our_items.get('medkit', 0) > 0
                and ActionType.USE_MEDKIT in legal):
            print(f"[MCTS-P{self.player_id}] HP={our_hp}, critical heal!")
            return ActionType.USE_MEDKIT

        # 3. Strategic freeze when we can exploit it
        if (our_items.get('freezeball', 0) > 0
                and our_balls >= 2 and opp_frozen == 0
                and combat_started
                and ActionType.USE_FREEZEBALL in legal):
            print(f"[MCTS-P{self.player_id}] Freezing (have {our_balls} balls)!")
            return ActionType.USE_FREEZEBALL

        # 4. Proactive dodge: sidestep when opponent aimed or in line
        if (opp_balls > 0 and opp_frozen == 0
                and h_dist == 0
                and our_last not in dodge_moves
                and opp_last == ActionType.AIM):
            mv = [a for a in legal if a in dodge_moves]
            if mv:
                centre = GameState.FIELD_WIDTH // 2
                best = min(mv, key=lambda a: abs(
                    (our_pos[0] - 1 if a == ActionType.MOVE_LEFT else
                     our_pos[0] + 1 if a == ActionType.MOVE_RIGHT else our_pos[0]) - centre))
                print(f"[MCTS-P{self.player_id}] Proactive dodge {best.name}!")
                return best

        # 5. Attack immediately when opponent just moved
        if (opp_last in dodge_moves and our_balls > 0
                and ActionType.THROW_SNOWBALL in legal
                and distance <= 6.0):
            print(f"[MCTS-P{self.player_id}] Attack window after opp moved!")
            return ActionType.THROW_SNOWBALL

        # ── Strategic filtering ───────────────────────────────────
        filtered = list(legal)
        if not combat_started and ActionType.USE_FREEZEBALL in filtered:
            filtered.remove(ActionType.USE_FREEZEBALL)
        if our_balls < 2 and ActionType.USE_FREEZEBALL in filtered:
            filtered.remove(ActionType.USE_FREEZEBALL)
        if our_hp_lost < 20 and ActionType.USE_MEDKIT in filtered:
            filtered.remove(ActionType.USE_MEDKIT)
        if not filtered:
            filtered = list(legal)

        # ── MCTS search ───────────────────────────────────────────
        root = self.search(state)

        if not root.children:
            return (ActionType.THROW_SNOWBALL if ActionType.THROW_SNOWBALL in filtered
                    else filtered[0])

        best_action = None
        best_value = -float('inf')
        best_visits = 0

        for action, child in root.children.items():
            if action not in filtered or child.visits == 0:
                continue
            avg = child.value / child.visits
            if avg > best_value:
                best_value = avg
                best_action = action
                best_visits = child.visits

        # Fallback to overall best
        if best_action is None:
            for action, child in root.children.items():
                if child.visits == 0: continue
                avg = child.value / child.visits
                if avg > best_value:
                    best_value = avg
                    best_action = action
                    best_visits = child.visits

        if best_action is None:
            best_action = filtered[0] if filtered else legal[0]

        print(f"[MCTS-P{self.player_id}] Nodes:{self.nodes_explored} "
              f"Visits:{best_visits} Value:{best_value:.3f} Action:{best_action.name}")
        return best_action