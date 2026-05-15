"""
Snowball Fight GUI — Fixed & Enhanced
  • Correct freeze/bonus-turn: attacker acts twice, victim skips turn
  • Proper dodge animation: ghost trail + destination tile highlight
  • Frozen aura with orbiting ice crystals and shake
  • Smart item HUD with icons
"""
import pygame, sys, os, time, math, random
from pathlib import Path
from game_state import GameState, ActionType
from game import SnowballGame
from enum import Enum


class GameScreen(Enum):
    MENU = 1
    GAMEPLAY = 2
    GAME_OVER = 3


def draw_rounded_box(surf, rect, fill, border, radius=10, border_width=2):
    pygame.draw.rect(surf, fill, rect, border_radius=radius)
    pygame.draw.rect(surf, border, rect, border_width, border_radius=radius)


class Button:
    HOVER_TINT = (255, 255, 255, 55)

    def __init__(self, image, x, y, w, h, callback, label=""):
        self.image = pygame.transform.smoothscale(image, (w, h)) if image else None
        self.rect = pygame.Rect(x, y, w, h)
        self.callback = callback
        self.label = label
        self.hovered = False

    def draw(self, screen, font):
        if self.image:
            img = self.image.copy()
            if self.hovered:
                tint = pygame.Surface(self.rect.size, pygame.SRCALPHA)
                tint.fill(self.HOVER_TINT)
                img.blit(tint, (0, 0))
            screen.blit(img, self.rect)
        else:
            fill = (70, 170, 70) if self.hovered else (45, 120, 45)
            draw_rounded_box(screen, self.rect, fill, (180, 255, 180), radius=10)
        if self.label and font:
            shadow = font.render(self.label, True, (0, 0, 0))
            screen.blit(shadow, shadow.get_rect(center=(self.rect.centerx + 1, self.rect.centery + 1)))
            txt = font.render(self.label, True, (255, 255, 255))
            screen.blit(txt, txt.get_rect(center=self.rect.center))

    def check_hover(self, pos): self.hovered = self.rect.collidepoint(pos)
    def check_click(self, pos):
        if self.rect.collidepoint(pos):
            self.callback()
            return True
        return False


class CompleteGameGUI:
    WHITE  = (255, 255, 255)
    BLACK  = (0,   0,   0)
    BLUE   = (50,  120, 220)
    RED    = (220, 60,  60)
    YELLOW = (255, 230, 0)
    CYAN   = (0,   210, 255)
    LIME   = (80,  255, 80)
    GRAY   = (100, 100, 100)
    ICE    = (140, 210, 255)
    ICE2   = (200, 235, 255)
    ORANGE = (255, 140, 0)
    GOLD   = (255, 200, 50)
    BG_FALLBACK = (34, 100, 34)

    WINDOW_WIDTH  = 1400
    WINDOW_HEIGHT = 800
    FIELD_PADDING = 40
    GRID_SIZE     = 120

    ACTION_DURATION   = 0.55
    SNOWBALL_DURATION = 0.55

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((self.WINDOW_WIDTH, self.WINDOW_HEIGHT))
        pygame.display.set_caption("Snowball Fight: AI vs AI")
        self.clock = pygame.time.Clock()

        self.font_xlarge = pygame.font.Font(None, 72)
        self.font_large  = pygame.font.Font(None, 52)
        self.font_medium = pygame.font.Font(None, 30)
        self.font_small  = pygame.font.Font(None, 22)
        self.font_huge   = pygame.font.Font(None, 68)

        self.current_screen = GameScreen.MENU
        self.game = None
        self.running = True
        self.paused = False
        self.game_speed = 1.0
        self.last_update = time.time()

        # ── Animation state ─────────────────────────────────────
        # Turn phases:
        #   "idle"            → call advance_turn, go to player_1_act
        #   "player_1_act"    → P1 normal action
        #   "player_1_bonus"  → P1 bonus turn (after freezeball)
        #   "player_2_act"    → P2 normal action (skipped if frozen)
        #   back to "idle"
        self.anim_phase = "idle"

        self.snowball_anim = None
        self.result_texts  = {}  # {key: {...}}
        self.dodge_anims   = {}  # {pid: {...}}
        self.frozen_shakes = {}

        self.action_log = []

        self.sprites = {}; self.backgrounds = {}; self.ui_images = {}
        self.load_assets()
        self.menu_buttons = []; self.game_over_buttons = []; self.gameplay_buttons = []
        self.create_menu_buttons()

    # ── Asset loading ────────────────────────────────────────────
    def load_assets(self):
        base = Path(__file__).parent.parent / "assets" / "images"
        for sub, store in [("sprites", self.sprites),
                            ("backgrounds", self.backgrounds),
                            ("ui", self.ui_images)]:
            d = base / sub
            if not d.exists():
                continue
            for f in sorted(d.glob("*.png")):
                try:
                    img = pygame.image.load(str(f))
                    img = img.convert_alpha() if sub != "backgrounds" else img.convert()
                    store[f.stem] = img
                except Exception:
                    pass

    # ── Coordinate helpers ───────────────────────────────────────
    def grid_to_pixel(self, gx, gy):
        return (self.FIELD_PADDING + gx * self.GRID_SIZE + self.GRID_SIZE // 2,
                self.FIELD_PADDING + gy * self.GRID_SIZE + self.GRID_SIZE // 2)

    # ── Buttons ──────────────────────────────────────────────────
    def create_menu_buttons(self):
        cx = self.WINDOW_WIDTH // 2
        bw, bh = 260, 58
        p = self.ui_images.get("button_play")
        e = self.ui_images.get("button_exit")
        self.menu_buttons = [
            Button(p, cx - bw//2, 300, bw, bh, lambda: self.start_game("minimax", "mcts"),    "Minimax vs MCTS"),
            Button(p, cx - bw//2, 380, bw, bh, lambda: self.start_game("mcts",    "mcts"),    "MCTS vs MCTS"),
            Button(p, cx - bw//2, 460, bw, bh, lambda: self.start_game("minimax", "minimax"), "Minimax vs Minimax"),
            Button(e, cx - 35,    560, 70,  70, self.quit_game, ""),
        ]

    def create_game_over_buttons(self):
        cx = self.WINDOW_WIDTH // 2
        bw, bh = 240, 58
        p = self.ui_images.get("button_play")
        e = self.ui_images.get("button_exit")
        self.game_over_buttons = [
            Button(p, cx - bw//2, 460, bw, bh, lambda: self.start_game("minimax", "mcts"), "Play Again"),
            Button(p, cx - bw//2, 540, bw, bh, self.go_to_menu,                            "Main Menu"),
            Button(e, cx - 35,    640, 70,  70, self.quit_game,                             ""),
        ]

    def create_gameplay_buttons(self):
        e = self.ui_images.get("button_exit")
        self.gameplay_buttons = [
            Button(None, 10,  10, 110, 36, self.toggle_pause,  "Pause"),
            Button(None, 130, 10,  90, 36, self.speed_up,      "Speed+"),
            Button(None, 230, 10,  90, 36, self.speed_down,    "Speed-"),
            Button(e, self.WINDOW_WIDTH - 52, 10, 42, 42, self.go_to_menu, ""),
        ]

    def quit_game(self):    self.running = False
    def go_to_menu(self):
        self.current_screen = GameScreen.MENU
        self.game = None
    def toggle_pause(self): self.paused = not self.paused
    def speed_up(self):     self.game_speed = min(4.0, self.game_speed + 0.25)
    def speed_down(self):   self.game_speed = max(0.1, self.game_speed - 0.25)

    # ── Background ───────────────────────────────────────────────
    def draw_background(self, key):
        bg = self.backgrounds.get(key)
        if bg:
            self.screen.blit(pygame.transform.smoothscale(bg, (self.WINDOW_WIDTH, self.WINDOW_HEIGHT)), (0, 0))
        else:
            self.screen.fill(self.BG_FALLBACK)

    # ── Grid ─────────────────────────────────────────────────────
    def draw_transparent_grid(self):
        x0, y0 = self.FIELD_PADDING, self.FIELD_PADDING
        w = GameState.FIELD_WIDTH  * self.GRID_SIZE
        h = GameState.FIELD_HEIGHT * self.GRID_SIZE

        field_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        field_surf.fill((255, 255, 255, 6))
        self.screen.blit(field_surf, (x0, y0))

        ov = pygame.Surface((w, h), pygame.SRCALPHA)
        gc = (255, 255, 255, 22)
        for i in range(GameState.FIELD_WIDTH + 1):
            pygame.draw.line(ov, gc, (i * self.GRID_SIZE, 0), (i * self.GRID_SIZE, h), 1)
        for j in range(GameState.FIELD_HEIGHT + 1):
            pygame.draw.line(ov, gc, (0, j * self.GRID_SIZE), (w, j * self.GRID_SIZE), 1)
        self.screen.blit(ov, (x0, y0))

        border = pygame.Surface((w + 4, h + 4), pygame.SRCALPHA)
        pygame.draw.rect(border, (100, 200, 255, 50), (0, 0, w + 4, h + 4), 2, border_radius=4)
        self.screen.blit(border, (x0 - 2, y0 - 2))

    # ── Player drawing ───────────────────────────────────────────
    def _interp_player_pos(self, pid) -> tuple:
        state = self.game.get_game_state()
        grid_pos = state.player1_pos if pid == 1 else state.player2_pos

        if pid in self.dodge_anims:
            da = self.dodge_anims[pid]
            elapsed = time.time() - da['start']
            t = min(1.0, elapsed / da['dur'])
            t_ease = 1.0 - (1.0 - t) ** 3
            fx, fy = self.grid_to_pixel(*da['from_pos'])
            tx, ty = self.grid_to_pixel(*da['to_pos'])
            return (int(fx + (tx - fx) * t_ease), int(fy + (ty - fy) * t_ease))

        return self.grid_to_pixel(*grid_pos)

    def _draw_dodge_effects(self):
        now = time.time()
        for pid, da in list(self.dodge_anims.items()):
            elapsed = now - da['start']
            t = min(1.0, elapsed / da['dur'])
            if t >= 1.0:
                continue

            fx, fy = self.grid_to_pixel(*da['from_pos'])
            tx, ty = self.grid_to_pixel(*da['to_pos'])

            ghost_alpha = int(180 * (1.0 - t))
            ghost_size = int(self.GRID_SIZE * 0.7)
            ghost_surf = pygame.Surface((ghost_size, ghost_size), pygame.SRCALPHA)
            ghost_color = (50, 120, 220, ghost_alpha) if pid == 1 else (220, 60, 60, ghost_alpha)
            pygame.draw.circle(ghost_surf, ghost_color, (ghost_size // 2, ghost_size // 2), ghost_size // 2)
            self.screen.blit(ghost_surf, ghost_surf.get_rect(center=(fx, fy)))

            dx_total = tx - fx
            dy_total = ty - fy
            dist_total = max(1, math.sqrt(dx_total**2 + dy_total**2))
            nx, ny = dx_total / dist_total, dy_total / dist_total
            pos_along = 0
            while pos_along < dist_total:
                seg_end = min(pos_along + 8, dist_total)
                sx = int(fx + nx * pos_along); sy = int(fy + ny * pos_along)
                ex = int(fx + nx * seg_end);   ey = int(fy + ny * seg_end)
                pygame.draw.line(self.screen, (80, 255, 80, int(200 * (1.0 - t))), (sx, sy), (ex, ey), 3)
                pos_along += 14

            tile_alpha = int(120 * (1.0 - t * 0.7))
            tile_surf = pygame.Surface((self.GRID_SIZE, self.GRID_SIZE), pygame.SRCALPHA)
            tile_surf.fill((80, 255, 80, tile_alpha))
            pygame.draw.rect(tile_surf, (120, 255, 120, min(255, tile_alpha + 60)),
                             (0, 0, self.GRID_SIZE, self.GRID_SIZE), 3, border_radius=6)
            tile_x = self.FIELD_PADDING + da['to_pos'][0] * self.GRID_SIZE
            tile_y = self.FIELD_PADDING + da['to_pos'][1] * self.GRID_SIZE
            self.screen.blit(tile_surf, (tile_x, tile_y))

    def draw_player(self, pid, flash=False, frozen=False, bonus_glow=False):
        px, py = self._interp_player_pos(pid)

        shake_x = shake_y = 0
        if pid in self.frozen_shakes:
            fs = self.frozen_shakes[pid]
            elapsed = time.time() - fs['start']
            if elapsed < fs['dur']:
                shake_x = int(math.sin(elapsed * 40) * 3)
            else:
                del self.frozen_shakes[pid]

        draw_x = px + shake_x
        draw_y = py + shake_y

        # ── Bonus turn golden glow ────────────────────────────────
        if bonus_glow:
            now = time.time()
            pulse = 0.80 + 0.20 * math.sin(now * 6)
            aura_r = int(self.GRID_SIZE * 0.70 * pulse)
            aura = pygame.Surface((aura_r * 2 + 4, aura_r * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(aura, (255, 220, 50, 80), (aura_r + 2, aura_r + 2), aura_r)
            pygame.draw.circle(aura, (255, 240, 100, 180), (aura_r + 2, aura_r + 2), aura_r, 3)
            self.screen.blit(aura, (draw_x - aura_r - 2, draw_y - aura_r - 2))

        # ── Frozen aura ───────────────────────────────────────────
        if frozen:
            now = time.time()
            pulse = 0.85 + 0.15 * math.sin(now * 4)
            aura_r = int(self.GRID_SIZE * 0.65 * pulse)
            aura = pygame.Surface((aura_r * 2 + 4, aura_r * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(aura, (100, 180, 255, 90), (aura_r + 2, aura_r + 2), aura_r)
            pygame.draw.circle(aura, (180, 230, 255, 160), (aura_r + 2, aura_r + 2), aura_r, 3)
            self.screen.blit(aura, (draw_x - aura_r - 2, draw_y - aura_r - 2))
            for i in range(6):
                angle = math.radians(i * 60 + now * 60)
                cx2 = draw_x + int(math.cos(angle) * aura_r)
                cy2 = draw_y + int(math.sin(angle) * aura_r)
                pygame.draw.circle(self.screen, self.ICE2, (cx2, cy2), 5)
                pygame.draw.line(self.screen, self.WHITE, (cx2 - 4, cy2), (cx2 + 4, cy2), 1)
                pygame.draw.line(self.screen, self.WHITE, (cx2, cy2 - 4), (cx2, cy2 + 4), 1)

        # ── Sprite ────────────────────────────────────────────────
        sp = self.sprites.get(f"player{pid}")
        sz = int(self.GRID_SIZE * 0.82)
        if sp:
            scaled = pygame.transform.smoothscale(sp, (sz, sz))
            self.screen.blit(scaled, scaled.get_rect(center=(draw_x, draw_y)))
        else:
            c = self.BLUE if pid == 1 else self.RED
            pygame.draw.circle(self.screen, c, (draw_x, draw_y), sz // 2)
            lbl = self.font_large.render(str(pid), True, self.WHITE)
            self.screen.blit(lbl, lbl.get_rect(center=(draw_x, draw_y)))

        # ── Hit flash ─────────────────────────────────────────────
        if flash:
            flash_s = pygame.Surface((sz, sz), pygame.SRCALPHA)
            flash_s.fill((255, 50, 50, 170))
            self.screen.blit(flash_s, flash_s.get_rect(center=(draw_x, draw_y)))

        # ── Labels ────────────────────────────────────────────────
        if frozen:
            label = self.font_small.render("FROZEN", True, self.ICE)
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                ol = self.font_small.render("FROZEN", True, (0, 0, 60))
                self.screen.blit(ol, ol.get_rect(center=(draw_x + dx, draw_y + sz // 2 + 8 + dy)))
            self.screen.blit(label, label.get_rect(center=(draw_x, draw_y + sz // 2 + 8)))

        if bonus_glow:
            blabel = self.font_small.render("BONUS!", True, self.GOLD)
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                ol = self.font_small.render("BONUS!", True, (80, 60, 0))
                self.screen.blit(ol, ol.get_rect(center=(draw_x + dx, draw_y - sz // 2 - 8 + dy)))
            self.screen.blit(blabel, blabel.get_rect(center=(draw_x, draw_y - sz // 2 - 8)))

    # ── Snowball projectile ───────────────────────────────────────
    def draw_snowball_projectile(self):
        if not self.snowball_anim:
            return
        now = time.time()
        a = self.snowball_anim
        elapsed = now - a['start']
        if elapsed > a['dur']:
            self.snowball_anim = None
            return

        t = min(1.0, elapsed / a['dur'])
        cx = a['sx'] + (a['ex'] - a['sx']) * t
        cy = a['sy'] + (a['ey'] - a['sy']) * t
        arc_h = -90 * a.get('force', 1.0)
        cy += arc_h * math.sin(t * math.pi)

        for i in range(1, 5):
            tt = max(0.0, t - 0.06 * i)
            tx = a['sx'] + (a['ex'] - a['sx']) * tt
            ty = (a['sy'] + (a['ey'] - a['sy']) * tt) + arc_h * math.sin(tt * math.pi)
            alpha = 160 - i * 38
            r = max(2, 8 - i * 2)
            trail = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(trail, (255, 255, 255, alpha), (r, r), r)
            self.screen.blit(trail, (int(tx) - r, int(ty) - r))

        if not a.get('is_hit', True) and 0.45 < t < 0.75:
            for angle in range(0, 360, 45):
                rad = math.radians(angle)
                sparkd = 22 * math.sin((t - 0.45) * math.pi / 0.3)
                sx2 = cx + math.cos(rad) * sparkd
                sy2 = cy + math.sin(rad) * sparkd
                pygame.draw.circle(self.screen, self.YELLOW, (int(sx2), int(sy2)), 3)

        sb = self.sprites.get("snowball")
        if sb:
            sz = int(self.GRID_SIZE * 0.38)
            sc = pygame.transform.smoothscale(sb, (sz, sz))
            sc = pygame.transform.rotate(sc, int(t * 360) % 360)
            self.screen.blit(sc, sc.get_rect(center=(int(cx), int(cy))))
        else:
            pygame.draw.circle(self.screen, self.WHITE, (int(cx), int(cy)), 11)
            pygame.draw.circle(self.screen, (200, 200, 255), (int(cx), int(cy)), 11, 2)

    # ── Floating popup text ───────────────────────────────────────
    def draw_result_text(self):
        now = time.time()
        done = []
        for key, r in self.result_texts.items():
            elapsed = now - r['start']
            if elapsed < 0: continue
            t = min(1.0, elapsed / r['dur'])
            if t >= 1.0:
                done.append(key)
                continue
            alpha = 255 if t < 0.65 else int(255 * (1.0 - (t - 0.65) / 0.35))
            y_off  = int(-50 * t)
            txt = self.font_huge.render(r['text'], True, r['color'])
            txt.set_alpha(alpha)
            self.screen.blit(txt, txt.get_rect(center=(r['x'], r['y'] + y_off)))
            sub = r.get('full_text', '')
            if sub and t < 0.75:
                sub_alpha = int(200 * (1.0 - t * 0.6))
                stxt = self.font_small.render(sub[:65], True, r['color'])
                stxt.set_alpha(sub_alpha)
                self.screen.blit(stxt, stxt.get_rect(center=(r['x'], r['y'] + y_off + 52)))
        for key in done:
            del self.result_texts[key]

    # ── HUD ──────────────────────────────────────────────────────
    def _draw_item_icons(self, x, y, items: dict, color):
        ix = x
        sz = 18
        has_freeze = items.get('freezeball', 0) > 0
        has_medkit  = items.get('medkit', 0) > 0

        if has_freeze:
            points = []
            for i in range(6):
                angle = math.radians(i * 60 - 30)
                points.append((ix + sz//2 + int(math.cos(angle) * sz//2),
                                y  + sz//2 + int(math.sin(angle) * sz//2)))
            pygame.draw.polygon(self.screen, self.ICE,  points)
            pygame.draw.polygon(self.screen, self.WHITE, points, 1)
            ix += sz + 6

        if has_medkit:
            r = pygame.Rect(ix, y, sz, sz)
            pygame.draw.rect(self.screen, (220, 50, 50), r, border_radius=3)
            arm = sz // 4
            mid = sz // 2
            pygame.draw.rect(self.screen, self.WHITE, pygame.Rect(ix + arm, y + 2, arm, sz - 4))
            pygame.draw.rect(self.screen, self.WHITE, pygame.Rect(ix + 2, y + arm, sz - 4, arm))
            ix += sz + 6

        if not has_freeze and not has_medkit:
            none_txt = self.font_small.render("no items", True, (160, 160, 160))
            self.screen.blit(none_txt, (x, y))

    def draw_hud(self, state: GameState):
        hud_y = self.WINDOW_HEIGHT - 160
        bar = pygame.Surface((self.WINDOW_WIDTH, 160), pygame.SRCALPHA)
        bar.fill((0, 0, 0, 195))
        self.screen.blit(bar, (0, hud_y))
        pygame.draw.line(self.screen, (80, 160, 255), (0, hud_y), (self.WINDOW_WIDTH, hud_y), 2)

        BW = 190

        # P1
        p1c = self.CYAN
        name1 = self.font_medium.render(f"P1: {self.game.agent1_type.upper()}", True, p1c)
        self.screen.blit(name1, (18, hud_y + 10))
        hp1_frac = max(0, state.player1_hp / GameState.INITIAL_HP)
        hp1_col  = self.LIME if hp1_frac > 0.5 else (self.YELLOW if hp1_frac > 0.25 else self.RED)
        pygame.draw.rect(self.screen, (50, 50, 50), (18, hud_y + 40, BW, 14), border_radius=7)
        pygame.draw.rect(self.screen, hp1_col,      (18, hud_y + 40, int(BW * hp1_frac), 14), border_radius=7)
        pygame.draw.rect(self.screen, p1c,           (18, hud_y + 40, BW, 14), 1, border_radius=7)
        hp1_lbl = self.font_small.render(f"HP: {state.player1_hp}  SB: {state.player1_snowballs}", True, p1c)
        self.screen.blit(hp1_lbl, (18, hud_y + 60))
        items_lbl = self.font_small.render("Items:", True, (200, 200, 200))
        self.screen.blit(items_lbl, (18, hud_y + 82))
        self._draw_item_icons(75, hud_y + 80, state.player1_items, p1c)
        if state.player1_frozen > 0:
            f1 = self.font_small.render(f"FROZEN ({state.player1_frozen} turns)", True, self.ICE)
            self.screen.blit(f1, (18, hud_y + 108))
        # Bonus turn indicator
        if state.pending_bonus_turn == 1:
            bt = self.font_small.render("⚡ BONUS TURN!", True, self.GOLD)
            self.screen.blit(bt, (18, hud_y + 126))

        # P2
        p2c = (255, 110, 110)
        name2 = self.font_medium.render(f"P2: {self.game.agent2_type.upper()}", True, p2c)
        self.screen.blit(name2, name2.get_rect(right=self.WINDOW_WIDTH - 18, top=hud_y + 10))
        hp2_frac = max(0, state.player2_hp / GameState.INITIAL_HP)
        hp2_col  = self.LIME if hp2_frac > 0.5 else (self.YELLOW if hp2_frac > 0.25 else self.RED)
        bx2 = self.WINDOW_WIDTH - 18 - BW
        pygame.draw.rect(self.screen, (50, 50, 50), (bx2, hud_y + 40, BW, 14), border_radius=7)
        pygame.draw.rect(self.screen, hp2_col,      (bx2, hud_y + 40, int(BW * hp2_frac), 14), border_radius=7)
        pygame.draw.rect(self.screen, p2c,           (bx2, hud_y + 40, BW, 14), 1, border_radius=7)
        hp2_lbl = self.font_small.render(f"HP: {state.player2_hp}  SB: {state.player2_snowballs}", True, p2c)
        self.screen.blit(hp2_lbl, hp2_lbl.get_rect(right=self.WINDOW_WIDTH - 18, top=hud_y + 60))
        items2_lbl = self.font_small.render("Items:", True, (200, 200, 200))
        self.screen.blit(items2_lbl, items2_lbl.get_rect(right=self.WINDOW_WIDTH - 18 - 4, top=hud_y + 82))
        self._draw_item_icons(self.WINDOW_WIDTH - 18 - BW, hud_y + 80, state.player2_items, p2c)
        if state.player2_frozen > 0:
            f2 = self.font_small.render(f"FROZEN ({state.player2_frozen} turns)", True, self.ICE)
            self.screen.blit(f2, f2.get_rect(right=self.WINDOW_WIDTH - 18, top=hud_y + 108))
        if state.pending_bonus_turn == 2:
            bt = self.font_small.render("⚡ BONUS TURN!", True, self.GOLD)
            self.screen.blit(bt, bt.get_rect(right=self.WINDOW_WIDTH - 18, top=hud_y + 126))

        # Centre
        # turn_txt = self.font_large.render(f"Turn: {state.current_turn}", True, self.YELLOW)
        # self.screen.blit(turn_txt, turn_txt.get_rect(center=(self.WINDOW_WIDTH // 2, hud_y + 22)))

        # Phase label
        phase_label = self.anim_phase.replace("_", " ").upper()
        if self.paused:
            st, sc = "PAUSED",    self.YELLOW
        elif state.is_game_over:
            st, sc = "GAME OVER", self.RED
        elif "bonus" in self.anim_phase:
            st, sc = f"BONUS TURN — {phase_label}", self.GOLD
        else:
            st, sc = "PLAYING",   self.LIME
        status_txt = self.font_medium.render(st, True, sc)
        self.screen.blit(status_txt, status_txt.get_rect(center=(self.WINDOW_WIDTH // 2, hud_y + 58)))

        log_y = hud_y + 90
        for msg in self.action_log[-2:]:
            if msg:
                mt = self.font_small.render(msg[:70], True, (220, 220, 220))
                self.screen.blit(mt, mt.get_rect(center=(self.WINDOW_WIDTH // 2, log_y)))
                log_y += 20

    # ── Menu screen ──────────────────────────────────────────────
    def draw_menu(self):
        self.draw_background("menu_bg")
        header = pygame.Surface((self.WINDOW_WIDTH, 230), pygame.SRCALPHA)
        header.fill((0, 0, 0, 145))
        self.screen.blit(header, (0, 30))
        title = self.font_xlarge.render("SNOWBALL FIGHT", True, self.WHITE)
        shadow = self.font_xlarge.render("SNOWBALL FIGHT", True, (0, 180, 220))
        self.screen.blit(shadow, shadow.get_rect(center=(self.WINDOW_WIDTH // 2 + 3, 103)))
        self.screen.blit(title,  title.get_rect(center=(self.WINDOW_WIDTH // 2, 100)))
        sub = self.font_large.render("AI vs AI Battle", True, self.CYAN)
        self.screen.blit(sub, sub.get_rect(center=(self.WINDOW_WIDTH // 2, 175)))
        for btn in self.menu_buttons:
            if btn.label:
                pill = pygame.Surface((btn.rect.width + 20, btn.rect.height + 10), pygame.SRCALPHA)
                pill.fill((0, 0, 0, 80))
                self.screen.blit(pill, (btn.rect.x - 10, btn.rect.y - 5))
            btn.draw(self.screen, self.font_medium)

    # ── Gameplay screen ──────────────────────────────────────────
    def draw_gameplay(self):
        self.draw_background("game_bg")
        if not self.game:
            return
        state = self.game.get_game_state()
        self.draw_transparent_grid()

        # Which player (if any) is currently in their bonus turn?
        bonus_pid = None
        if "bonus" in self.anim_phase:
            try:
                bonus_pid = int(self.anim_phase.split("_")[1])
            except Exception:
                pass

        p1_flash  = 1 in self.result_texts and "HIT" in self.result_texts[1].get('text', '')
        p2_flash  = 2 in self.result_texts and "HIT" in self.result_texts[2].get('text', '')

        self.draw_player(1, flash=p1_flash, frozen=state.player1_frozen > 0, bonus_glow=(bonus_pid == 1))
        self.draw_player(2, flash=p2_flash, frozen=state.player2_frozen > 0, bonus_glow=(bonus_pid == 2))
        self._draw_dodge_effects()
        self.draw_snowball_projectile()
        self.draw_result_text()
        self.draw_hud(state)
        for btn in self.gameplay_buttons:
            btn.draw(self.screen, self.font_small)

    # ── Game-over screen ─────────────────────────────────────────
    def draw_game_over(self):
        self.draw_background("game_bg")
        ov = pygame.Surface((self.WINDOW_WIDTH, self.WINDOW_HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 185))
        self.screen.blit(ov, (0, 0))
        state = self.game.get_game_state()
        go = self.font_xlarge.render("GAME OVER", True, self.RED)
        self.screen.blit(go, go.get_rect(center=(self.WINDOW_WIDTH // 2, 90)))
        if state.winner == 1:
            wt, wc = f"Player 1 ({self.game.agent1_type.upper()}) WINS!", self.CYAN
        elif state.winner == 2:
            wt, wc = f"Player 2 ({self.game.agent2_type.upper()}) WINS!", (255, 110, 110)
        else:
            wt, wc = "IT'S A DRAW!", self.YELLOW
        wl = self.font_large.render(wt, True, wc)
        self.screen.blit(wl, wl.get_rect(center=(self.WINDOW_WIDTH // 2, 185)))
        for i, s in enumerate([
            f"Turns: {state.current_turn}",
            f"P1 HP: {state.player1_hp}     P2 HP: {state.player2_hp}",
            f"P1 Items left: {state.player1_items}",
            f"P2 Items left: {state.player2_items}",
        ]):
            lt = self.font_medium.render(s, True, self.WHITE)
            self.screen.blit(lt, lt.get_rect(center=(self.WINDOW_WIDTH // 2, 290 + i * 48)))
        for btn in self.game_over_buttons:
            btn.draw(self.screen, self.font_medium)

    # ── Events ───────────────────────────────────────────────────
    def handle_events(self):
        mp = pygame.mouse.get_pos()
        btns = {
            GameScreen.MENU:      self.menu_buttons,
            GameScreen.GAMEPLAY:  self.gameplay_buttons,
            GameScreen.GAME_OVER: self.game_over_buttons,
        }.get(self.current_screen, [])
        for b in btns: b.check_hover(mp)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for b in btns: b.check_click(event.pos)
            elif event.type == pygame.KEYDOWN:
                self._handle_key(event.key)

    def _handle_key(self, key):
        if self.current_screen == GameScreen.MENU:
            if key == pygame.K_1:    self.start_game("minimax", "mcts")
            elif key == pygame.K_2:  self.start_game("mcts",    "mcts")
            elif key == pygame.K_3:  self.start_game("minimax", "minimax")
            elif key == pygame.K_q:  self.running = False
        elif self.current_screen == GameScreen.GAMEPLAY:
            if key == pygame.K_SPACE:  self.toggle_pause()
            elif key == pygame.K_UP:   self.speed_up()
            elif key == pygame.K_DOWN: self.speed_down()
            elif key == pygame.K_q:    self.go_to_menu()
        elif self.current_screen == GameScreen.GAME_OVER:
            if key == pygame.K_1:    self.start_game("minimax", "mcts")
            elif key == pygame.K_m:  self.go_to_menu()
            elif key == pygame.K_q:  self.running = False

    # ── Game start ───────────────────────────────────────────────
    def start_game(self, a1, a2):
        print(f"\nStarting: {a1} vs {a2}")
        self.game = SnowballGame(agent1_type=a1, agent2_type=a2)
        self.current_screen = GameScreen.GAMEPLAY
        self.paused = False
        self.game_speed = 1.0
        self.last_update = time.time()
        self.anim_phase    = "idle"
        self.snowball_anim = None
        self.result_texts  = {}
        self.dodge_anims   = {}
        self.frozen_shakes = {}
        self.action_log    = []
        self.create_gameplay_buttons()

    # ── Action helpers ───────────────────────────────────────────
    def _play_single_action(self, player_id):
        state = self.game.state
        agent = self.game.agent1 if player_id == 1 else self.game.agent2
        action = agent.get_best_action(state)
        result = state.apply_action(player_id, action)
        state.check_game_over()
        return action, result

    def _start_throw_animation(self, thrower_id, result, aimed_pos=None):
        state = self.game.state
        force  = result.get('throw_force', 1.0)
        is_hit = result.get('hit', False)
        sp = self.grid_to_pixel(*(state.player1_pos if thrower_id == 1 else state.player2_pos))

        if aimed_pos:
            aimed_pixel = self.grid_to_pixel(*aimed_pos)
        else:
            target_pos = state.player2_pos if thrower_id == 1 else state.player1_pos
            aimed_pixel = self.grid_to_pixel(*target_pos)

        if not is_hit:
            scatter_x = random.choice([-25, 25])
            ep = (aimed_pixel[0] + scatter_x, aimed_pixel[1] + random.randint(-15, 15))
        else:
            ep = aimed_pixel

        dur = max(0.35, 0.35 + force * 0.25)
        self.snowball_anim = {
            'sx': sp[0], 'sy': sp[1], 'ex': ep[0], 'ey': ep[1],
            'start': time.time(), 'dur': dur,
            'player_id': thrower_id, 'force': force, 'is_hit': is_hit
        }

    def _start_dodge_animation(self, dodger_id, from_pos, to_pos):
        self.dodge_anims[dodger_id] = {
            'from_pos': list(from_pos),
            'to_pos':   list(to_pos),
            'start':    time.time(),
            'dur':      0.45,
        }

    def _start_frozen_shake(self, pid):
        self.frozen_shakes[pid] = {'start': time.time(), 'dur': 0.5}

    def _create_result_popup(self, result, target_id, delay=0.0, key=None):
        state = self.game.state
        pos = state.player1_pos if target_id == 1 else state.player2_pos
        px, py = self.grid_to_pixel(*pos)

        if result.get('hit', False):
            txt, color, dur = f"HIT! -{result['damage']} HP", self.RED, 1.2
        elif result.get('freeze_applied', False):
            txt, color, dur = "FROZEN!", self.ICE, 1.4
        elif result.get('bonus_turn_granted', False):
            txt, color, dur = "BONUS TURN!", self.GOLD, 1.3
        elif result.get('item_used') == 'medkit':
            txt, color, dur = f"+{result.get('heal_amount', 30)} HP", self.LIME, 1.2
        else:
            txt, color, dur = "DODGED!", self.LIME, 1.3

        popup_key = key if key is not None else target_id
        self.result_texts[popup_key] = {
            'text':      txt,
            'color':     color,
            'x':         px,
            'y':         py - 50,
            'start':     time.time() + delay,
            'dur':       dur,
            'full_text': result.get('message', ''),
        }

    def _animations_running(self) -> bool:
        if self.snowball_anim:
            return True
        now = time.time()
        for r in self.result_texts.values():
            if now - r['start'] < r['dur']:
                return True
        stale = [k for k, da in self.dodge_anims.items()
                 if time.time() - da['start'] >= da['dur']]
        for k in stale:
            del self.dodge_anims[k]
        if self.dodge_anims:
            return True
        return False

    # ── Game update — step-by-step with correct bonus-turn flow ──
    #
    # Phase sequence:
    #   idle
    #     → advance_turn
    #     → player_1_act
    #       If P1 used freezeball → player_1_bonus (P1 gets bonus turn)
    #       else → player_2_act  (P2 may be frozen/skipped)
    #     → player_2_act
    #       → idle
    #
    def update_game(self):
        if not self.game or self.paused:
            return
        state = self.game.get_game_state()
        if state.is_game_over:
            if self._animations_running():
                return
            if self.current_screen != GameScreen.GAME_OVER:
                self.current_screen = GameScreen.GAME_OVER
                self.create_game_over_buttons()
            return

        now = time.time()
        if self._animations_running():
            return

        turn_delay = self.ACTION_DURATION / self.game_speed
        if now - self.last_update < turn_delay:
            return

        # ── IDLE: start a new round ────────────────────────────────
        if self.anim_phase == "idle":
            state.advance_turn()
            self.anim_phase = "player_1_act"
            self.last_update = now
            return

        # ── PLAYER ACTION PHASES ───────────────────────────────────
        parts = self.anim_phase.split("_")
        # parts: ["player", "N", "act"|"bonus"] or ["player", "N", "bonus"]
        try:
            current_player = int(parts[1])
        except (IndexError, ValueError):
            self.anim_phase = "idle"
            return

        is_bonus = len(parts) > 2 and parts[2] == "bonus"

        # ── Check if this player is frozen and should be skipped ───
        frozen = state.player1_frozen if current_player == 1 else state.player2_frozen
        if frozen > 0 and not is_bonus:
            # Skip this player's turn, tick their counter
            self.action_log.append(f"P{current_player} FROZEN — SKIPPED! ({frozen} turns left)")
            state.tick_frozen(current_player)
            # Advance to next player or idle
            if current_player == 1:
                self.anim_phase = "player_2_act"
            else:
                self.anim_phase = "idle"
            self.last_update = now
            return

        # ── Execute the action ─────────────────────────────────────
        pre_pos = list(state.player1_pos if current_player == 1 else state.player2_pos)
        action, result = self._play_single_action(current_player)
        post_pos = list(state.player1_pos if current_player == 1 else state.player2_pos)

        tag = "[BONUS]" if is_bonus else ""
        self.action_log.append(f"P{current_player}{tag}: {result['message']}")

        # ── Animate the action ─────────────────────────────────────
        if action == ActionType.THROW_SNOWBALL:
            target_id = 2 if current_player == 1 else 1
            tgt_curr = list(state.player2_pos if current_player == 1 else state.player1_pos)
            if not result.get('hit', True):
                dodge_dir = random.choice([-1, 1])
                dodge_to = list(tgt_curr)
                dodge_to[0] = max(0, min(GameState.FIELD_WIDTH - 1, tgt_curr[0] + dodge_dir))
                if dodge_to == tgt_curr:
                    dodge_to[0] = max(0, min(GameState.FIELD_WIDTH - 1, tgt_curr[0] - dodge_dir))
                self._start_dodge_animation(target_id, tgt_curr, dodge_to)
                self._start_throw_animation(current_player, result, aimed_pos=tgt_curr)
            else:
                self._start_throw_animation(current_player, result)
            travel_delay = self.snowball_anim['dur'] * 0.8 if self.snowball_anim else 0.4
            self._create_result_popup(result, target_id, delay=travel_delay)

        elif action == ActionType.USE_FREEZEBALL and result.get('freeze_applied'):
            target_id = 2 if current_player == 1 else 1
            self._start_frozen_shake(target_id)
            # Show FROZEN popup on target
            self._create_result_popup(result, target_id, delay=0.1)
            # Show BONUS TURN popup on attacker
            bonus_result = {'bonus_turn_granted': True, 'message': f'P{current_player} BONUS TURN!'}
            self._create_result_popup(bonus_result, current_player, delay=0.3,
                                      key=f"bonus_{current_player}")

        elif action in (ActionType.USE_MEDKIT,) and result.get('item_used') == 'medkit':
            self._create_result_popup(result, current_player, delay=0.1)

        elif action in (ActionType.MOVE_LEFT, ActionType.MOVE_RIGHT,
                        ActionType.MOVE_FORWARD, ActionType.MOVE_BACKWARD):
            if pre_pos != post_pos:
                self._start_dodge_animation(current_player, pre_pos, post_pos)
                move_dir = action.name.replace('MOVE_', '')
                px2, py2 = self.grid_to_pixel(*post_pos)
                self.result_texts[f"move_{current_player}"] = {
                    'text':      f'>> {move_dir}',
                    'color':     (120, 255, 120),
                    'x': px2, 'y': py2 - 60,
                    'start':     time.time(), 'dur': 0.6, 'full_text': '',
                }

        # ── Determine next phase ───────────────────────────────────
        # Did this action grant a bonus turn?
        bonus_granted = result.get('bonus_turn_granted') and state.pending_bonus_turn == current_player

        if bonus_granted and not is_bonus:
            # Consume the pending bonus turn flag and go to bonus phase
            state.consume_bonus_turn(current_player)
            self.anim_phase = f"player_{current_player}_bonus"

        elif current_player == 1:
            # P1 done — next is P2
            self.anim_phase = "player_2_act"

        else:
            # P2 done — round complete
            self.anim_phase = "idle"

        self.last_update = now
        state.check_game_over()

    # ── Main loop ────────────────────────────────────────────────
    def draw(self):
        if self.current_screen == GameScreen.MENU:
            self.draw_menu()
        elif self.current_screen == GameScreen.GAMEPLAY:
            self.draw_gameplay()
        elif self.current_screen == GameScreen.GAME_OVER:
            self.draw_game_over()
        pygame.display.flip()

    def run(self):
        print("\nControls: 1/2/3 = start | SPACE = pause | UP/DOWN = speed | Q = quit\n")
        while self.running:
            self.handle_events()
            self.update_game()
            self.draw()
            self.clock.tick(60)
        print("Thanks for playing!")
        pygame.quit()


def main():
    gui = CompleteGameGUI()
    gui.run()


if __name__ == "__main__":
    main()