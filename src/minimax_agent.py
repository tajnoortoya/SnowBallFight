"""
Minimax AI Agent with Alpha-Beta Pruning — Optimized Tactical v4

Key improvements:
  - Proper freeze double-turn: freezeball gives us 1 guaranteed bonus throw
  - Smart dodge prediction: move away BEFORE opponent throws (not after)
  - Aim optimization: prefer columns with lower hit chance for opponent
  - Attack timing: lead with throw when opponent just moved (they can't dodge again)
  - Medkit threshold: heal when it's efficient AND we have breathing room
"""

import random
from typing import Tuple, Optional
from game_state import GameState, ActionType


class MinimaxAgent:
    def __init__(self, player_id: int, depth: int = 3):
        self.player_id = player_id
        self.opponent_id = 2 if player_id == 1 else 1
        self.depth = depth
        self.nodes_explored = 0

    # ──────────────────────────────────────────────────────────────
    # Evaluation function
    # ──────────────────────────────────────────────────────────────
    def evaluate(self, state: GameState) -> float:
        if state.is_game_over:
            if state.winner == self.player_id:   return 10000
            if state.winner == self.opponent_id: return -10000
            return 0

        if self.player_id == 1:
            our_hp, opp_hp = state.player1_hp, state.player2_hp
            our_pos, opp_pos = state.player1_pos, state.player2_pos
            our_balls, opp_balls = state.player1_snowballs, state.player2_snowballs
            our_items, opp_items = state.player1_items, state.player2_items
            opp_frozen, our_frozen = state.player2_frozen, state.player1_frozen
            our_last = state.last_action_p1
            opp_last = state.last_action_p2
        else:
            our_hp, opp_hp = state.player2_hp, state.player1_hp
            our_pos, opp_pos = state.player2_pos, state.player1_pos
            our_balls, opp_balls = state.player2_snowballs, state.player1_snowballs
            our_items, opp_items = state.player2_items, state.player1_items
            opp_frozen, our_frozen = state.player1_frozen, state.player2_frozen
            our_last = state.last_action_p2
            opp_last = state.last_action_p1

        score = 0.0
        our_hp_lost = GameState.INITIAL_HP - our_hp
        opp_hp_lost = GameState.INITIAL_HP - opp_hp

        # 1. HP difference — primary objective
        score += (our_hp - opp_hp) * 15

        # 2. Snowball resource advantage
        score += (our_balls - opp_balls) * 8

        # 3. Frozen opponent advantage
        if opp_frozen > 0:
            # Guaranteed hit on next throw (100% chance); bonus turn already accounted for
            score += 80 + our_balls * 20
        if our_frozen > 0:
            score -= 80 + opp_balls * 20

        # 4. Pending bonus turn
        if state.pending_bonus_turn == self.player_id:
            score += 50  # about to get an extra guaranteed shot

        # 5. Positional scoring
        h_dist = abs(our_pos[0] - opp_pos[0])
        v_dist = abs(our_pos[1] - opp_pos[1])
        euclid = (h_dist**2 + v_dist**2) ** 0.5
        dodge_moves = {ActionType.MOVE_LEFT, ActionType.MOVE_RIGHT,
                       ActionType.MOVE_FORWARD, ActionType.MOVE_BACKWARD}

        if our_balls > 0:
            if opp_frozen > 0:
                # Want to be in line (h_dist=0) for straight shot guaranteed hit
                score -= h_dist * 12
            else:
                # Sweet spot: 1-2 columns off (harder to aim, easier for us to dodge)
                optimal_h = 1
                score -= abs(h_dist - optimal_h) * 4

        # Dodge scoring: offset from opponent column = harder to hit us
        if opp_balls > 0 and our_frozen == 0:
            if h_dist == 0:
                score -= 18   # directly in line = sitting duck
            elif h_dist == 1:
                score += 8    # slight offset = good dodge position
            elif h_dist <= 3:
                score += 5
            else:
                score -= 3    # too far = wasted throws

            # Centre position = more dodge options
            centre_dist = abs(our_pos[0] - GameState.FIELD_WIDTH // 2)
            if centre_dist <= 1:
                score += 6
            elif centre_dist >= 4:
                score -= 5   # near edge = trapped

            # Active dodge bonus: if we just moved, opponent aims at old position
            if our_last in dodge_moves:
                score += 12  # recent move = live dodge advantage

            # Penalise standing still while threatened
            if our_last in (ActionType.AIM, ActionType.THROW_SNOWBALL):
                score -= 5

        # 6. Opponent last action prediction
        # If opp just threw → they wasted their snowball this turn → safe to attack
        if opp_last == ActionType.THROW_SNOWBALL and our_balls > 0:
            score += 6   # window of opportunity

        # If opp just moved → they have dodge advantage → consider dodging too
        if opp_last in dodge_moves and our_balls > 0:
            score -= 3   # throwing now is slightly riskier (they might dodge again)

        # 7. Item valuation
        freeze_count = our_items.get('freezeball', 0)
        medkit_count = our_items.get('medkit', 0)
        combat_started = our_hp_lost > 0 or opp_hp_lost > 0 or our_balls < GameState.SNOWBALL_LIMIT

        if freeze_count > 0:
            if our_balls >= 2 and opp_frozen == 0 and combat_started:
                # 1 guaranteed throw + opponent skip = huge swing
                freeze_val = GameState.HIT_DAMAGE * 2.2
            elif our_balls >= 1 and opp_frozen == 0 and combat_started:
                freeze_val = GameState.HIT_DAMAGE * 1.2
            else:
                freeze_val = 3 if combat_started else -5
        else:
            freeze_val = 0

        if medkit_count > 0:
            if our_hp <= 30:
                medkit_val = 50 + our_hp_lost * 0.5
            elif our_hp_lost >= 30:
                medkit_val = 28 + our_hp_lost * 0.3
            elif our_hp_lost >= 20:
                medkit_val = 10
            else:
                medkit_val = -5
        else:
            medkit_val = 0

        score += freeze_val + medkit_val
        return score

    # ──────────────────────────────────────────────────────────────
    # Minimax with alpha-beta
    # ──────────────────────────────────────────────────────────────
    def minimax(self, state: GameState, depth: int, alpha: float, beta: float,
                is_maximizing: bool) -> Tuple[float, Optional[ActionType]]:
        self.nodes_explored += 1

        if depth == 0 or state.is_game_over:
            return self.evaluate(state), None

        player = self.player_id if is_maximizing else self.opponent_id
        frozen = state.player1_frozen if player == 1 else state.player2_frozen

        # Frozen: skip turn, tick counter
        if frozen > 0:
            ns = state.copy()
            ns.tick_frozen(player)
            if depth > 1:
                ns.advance_turn()
            return self.minimax(ns, depth - 1, alpha, beta, not is_maximizing)

        legal_actions = state.get_legal_actions(player)

        if is_maximizing:
            max_eval, best_action = float('-inf'), None
            for action in legal_actions:
                ns = state.copy()
                result = ns.apply_action(player, action)
                # Handle bonus turn inline during tree search
                if result.get('bonus_turn_granted') and ns.pending_bonus_turn == player:
                    ns.consume_bonus_turn(player)
                    bonus_legal = ns.get_legal_actions(player)
                    # Try all bonus actions and take the best
                    for bonus_action in bonus_legal:
                        ns2 = ns.copy()
                        ns2.apply_action(player, bonus_action)
                        if depth > 1: ns2.advance_turn()
                        ev, _ = self.minimax(ns2, depth - 1, alpha, beta, False)
                        if ev > max_eval:
                            max_eval = ev
                            best_action = action
                        alpha = max(alpha, ev)
                        if beta <= alpha: break
                else:
                    if depth > 1: ns.advance_turn()
                    ev, _ = self.minimax(ns, depth - 1, alpha, beta, False)
                    if ev > max_eval:
                        max_eval = ev
                        best_action = action
                    alpha = max(alpha, ev)
                    if beta <= alpha: break
            return max_eval, best_action
        else:
            min_eval, best_action = float('inf'), None
            for action in legal_actions:
                ns = state.copy()
                result = ns.apply_action(player, action)
                if result.get('bonus_turn_granted') and ns.pending_bonus_turn == player:
                    ns.consume_bonus_turn(player)
                    bonus_legal = ns.get_legal_actions(player)
                    for bonus_action in bonus_legal:
                        ns2 = ns.copy()
                        ns2.apply_action(player, bonus_action)
                        if depth > 1: ns2.advance_turn()
                        ev, _ = self.minimax(ns2, depth - 1, alpha, beta, True)
                        if ev < min_eval:
                            min_eval = ev
                            best_action = action
                        beta = min(beta, ev)
                        if beta <= alpha: break
                else:
                    if depth > 1: ns.advance_turn()
                    ev, _ = self.minimax(ns, depth - 1, alpha, beta, True)
                    if ev < min_eval:
                        min_eval = ev
                        best_action = action
                    beta = min(beta, ev)
                    if beta <= alpha: break
            return min_eval, best_action

    # ──────────────────────────────────────────────────────────────
    # Public interface
    # ──────────────────────────────────────────────────────────────
    def get_best_action(self, state: GameState) -> ActionType:
        self.nodes_explored = 0

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

        # ── Hard overrides (no-brainer situations) ───────────────

        # 1. EXPLOIT frozen opponent: guaranteed hit (100% chance)
        if opp_frozen > 0 and our_balls > 0 and ActionType.THROW_SNOWBALL in legal:
            print(f"[Minimax-P{self.player_id}] Opponent FROZEN — guaranteed throw!")
            return ActionType.THROW_SNOWBALL

        # 2. Critical heal when near death
        if (our_hp <= 40 and our_hp_lost >= 25
                and our_items.get('medkit', 0) > 0
                and ActionType.USE_MEDKIT in legal):
            print(f"[Minimax-P{self.player_id}] HP={our_hp}, critical heal!")
            return ActionType.USE_MEDKIT

        # 3. Use freezeball when we can exploit it immediately
        if (our_items.get('freezeball', 0) > 0
                and our_balls >= 2 and opp_frozen == 0
                and combat_started
                and ActionType.USE_FREEZEBALL in legal):
            print(f"[Minimax-P{self.player_id}] Freezing (have {our_balls} balls)!")
            return ActionType.USE_FREEZEBALL

        # 4. PROACTIVE DODGE: opponent has snowballs and we're standing still in their line
        if (opp_balls > 0 and opp_frozen == 0
                and h_dist == 0
                and our_last not in dodge_moves
                and opp_last == ActionType.AIM):  # opponent aimed = about to throw
            # Move away before they fire
            move_opts = [a for a in legal if a in dodge_moves]
            if move_opts:
                # Prefer moving toward centre
                centre = GameState.FIELD_WIDTH // 2
                best_move = None
                best_h = abs(our_pos[0] - centre)
                for mv in move_opts:
                    new_x = our_pos[0]
                    if mv == ActionType.MOVE_LEFT:  new_x -= 1
                    if mv == ActionType.MOVE_RIGHT: new_x += 1
                    nh = abs(new_x - centre)
                    if nh < best_h:
                        best_h = nh
                        best_move = mv
                if best_move is None:
                    best_move = random.choice(move_opts)
                print(f"[Minimax-P{self.player_id}] Proactive dodge {best_move.name}!")
                return best_move

        # 5. Attack immediately when opponent just moved (dodge advantage is on us now)
        if (opp_last in dodge_moves and our_balls > 0
                and ActionType.THROW_SNOWBALL in legal
                and h_dist <= 2):
            # They just moved → their prev-pos dodge bonus is gone next throw
            # Actually we should throw now before they move again
            if distance <= 6.0:  # reasonable range
                print(f"[Minimax-P{self.player_id}] Opp just moved — attack window!")
                return ActionType.THROW_SNOWBALL

        # ── Strategic action filtering ────────────────────────────
        filtered = list(legal)

        # Don't freeze if combat hasn't started
        if not combat_started and ActionType.USE_FREEZEBALL in filtered:
            filtered.remove(ActionType.USE_FREEZEBALL)

        # Don't freeze if we can't exploit it well
        if our_balls < 2 and ActionType.USE_FREEZEBALL in filtered:
            filtered.remove(ActionType.USE_FREEZEBALL)

        # Don't heal if barely hurt
        if our_hp_lost < 20 and ActionType.USE_MEDKIT in filtered:
            filtered.remove(ActionType.USE_MEDKIT)

        # If completely out of range, don't throw (save snowballs)
        if distance > 8.0 and ActionType.THROW_SNOWBALL in filtered and our_balls <= 2:
            filtered.remove(ActionType.THROW_SNOWBALL)

        if not filtered:
            filtered = list(legal)

        if len(filtered) == 1:
            return filtered[0]

        # ── Minimax search ────────────────────────────────────────
        best_score = float('-inf')
        best_action = filtered[0]

        for action in filtered:
            ns = state.copy()
            result = ns.apply_action(self.player_id, action)
            # Simulate bonus turn with best greedy action
            if result.get('bonus_turn_granted'):
                ns.consume_bonus_turn(self.player_id)
                bonus_legal = ns.get_legal_actions(self.player_id)
                # Greedy: throw if possible (frozen opp = guaranteed hit)
                bonus_action = (ActionType.THROW_SNOWBALL
                                if ActionType.THROW_SNOWBALL in bonus_legal
                                else bonus_legal[0])
                ns.apply_action(self.player_id, bonus_action)
            ns.advance_turn()
            score, _ = self.minimax(ns, self.depth - 1,
                                    float('-inf'), float('inf'), False)
            if score > best_score:
                best_score = score
                best_action = action

        print(f"[Minimax-P{self.player_id}] Nodes:{self.nodes_explored} "
              f"Score:{best_score:.1f} Action:{best_action.name}")
        return best_action