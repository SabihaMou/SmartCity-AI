"""SmartCity AI — reproducible traffic-signal simulation and visual analytics.

All traffic and outcomes are synthetic. No machine-learning model is trained.
"""
from __future__ import annotations
import csv
import math
import random
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import pygame

WIDTH, HEIGHT = 1360, 830
FPS = 60
ROAD_X, ROAD_Y = 425, 405
ROAD_W = 164
BG = (8, 14, 30)
PANEL = (17, 27, 48)
PANEL2 = (22, 35, 59)
BORDER = (45, 62, 92)
WHITE = (232, 240, 255)
MUTED = (145, 165, 197)
CYAN = (65, 218, 239)
PURPLE = (159, 119, 252)
GREEN = (75, 226, 161)
AMBER = (255, 194, 91)
RED = (250, 103, 130)

@dataclass
class Vehicle:
    lane: str
    arrival: float
    color: tuple[int, int, int]
    progress: float = 0.0

class Simulation:
    """Two conflicting movements, with four approach queues and stochastic arrivals."""
    def __init__(self, seed=17, demand=1.0, mode='Adaptive'):
        self.seed, self.demand, self.mode = seed, demand, mode
        self.rng = random.Random(seed)
        self.time = 0.0
        self.phase = 'NS'
        self.phase_elapsed = 0.0
        self.yellow_left = 0.0
        self.clearance_left = 0.0
        self.queues = {d: deque() for d in ('N', 'S', 'E', 'W')}
        self.next_arrival = {}
        self.spawned = self.completed = 0
        self.wait_total = 0.0
        self.wait_max = 0.0
        self.wait_samples = []
        self.queue_samples = []
        self.throughput_samples = []
        self.departures = deque(maxlen=40)
        self.moving = []
        self.last_discharge = {d: -100.0 for d in self.queues}
        self.switches = 0
        self.history_clock = 0.0
        for lane in self.queues:
            self.next_arrival[lane] = self.rng.expovariate(self.rate(lane))

    def rate(self, lane):
        # vehicles per second, different directional loads
        return self.demand * (0.19 if lane in 'NS' else 0.13)

    def total_queue(self):
        return sum(len(q) for q in self.queues.values())

    def movement_queue(self, phase):
        return sum(len(self.queues[d]) for d in phase)

    def avg_wait(self):
        return self.wait_total / self.completed if self.completed else 0.0

    def step(self, dt):
        self.time += dt
        self.phase_elapsed += dt
        self.history_clock += dt
        # Independent, seed-controlled Poisson arrivals
        for lane in self.queues:
            while self.next_arrival[lane] <= self.time:
                if len(self.queues[lane]) < 30:
                    self.queues[lane].append(Vehicle(lane, self.next_arrival[lane],
                                                      self.rng.choice((CYAN, PURPLE, GREEN, AMBER, (240, 241, 255)))))
                    self.spawned += 1
                self.next_arrival[lane] += self.rng.expovariate(self.rate(lane))
        if self.yellow_left > 0:
            self.yellow_left -= dt
            if self.yellow_left <= 0:
                self.yellow_left = 0
                self.clearance_left = 0.7
            return
        if self.clearance_left > 0:
            self.clearance_left -= dt
            if self.clearance_left <= 0:
                self.phase = 'EW' if self.phase == 'NS' else 'NS'
                self.phase_elapsed = 0.0
                self.switches += 1
            return
        active, other = self.movement_queue(self.phase), self.movement_queue('EW' if self.phase == 'NS' else 'NS')
        should_switch = False
        if self.mode == 'Fixed-time':
            should_switch = self.phase_elapsed >= 16.0
        else:
            # Actuated queue-responsive policy, min/max greens and fairness guard.
            if self.phase_elapsed >= 28:
                should_switch = True
            elif self.phase_elapsed >= 7:
                should_switch = (active == 0 and other > 0) or (other >= max(4, active * 1.6) and self.phase_elapsed >= 10)
        if should_switch:
            self.yellow_left = 1.6
            return
        for lane in self.phase:
            if self.queues[lane] and self.time - self.last_discharge[lane] >= 1.9:
                car = self.queues[lane].popleft()
                wait = max(0, self.time - car.arrival)
                self.wait_total += wait
                self.wait_max = max(self.wait_max, wait)
                self.completed += 1
                self.last_discharge[lane] = self.time
                self.departures.append(self.time)
                self.moving.append([lane, car.color, 0.0])
        for car in self.moving:
            car[2] += dt * 155
        self.moving = [car for car in self.moving if car[2] < 440]
        if self.history_clock >= 2:
            self.history_clock = 0
            self.queue_samples.append((self.time, self.total_queue()))
            self.wait_samples.append((self.time, self.avg_wait()))
            self.throughput_samples.append((self.time, self.completed))


def compare(seed, demand, horizon=240):
    """Paired common-random-numbers experiment: identical arrivals per approach."""
    results = {}
    for mode in ('Fixed-time', 'Adaptive'):
        sim = Simulation(seed, demand, mode)
        for _ in range(int(horizon / 0.1)):
            sim.step(0.1)
        results[mode] = sim
    return results


def text(surf, s, x, y, size=18, color=WHITE, bold=False, font=None):
    f = font or pygame.font.SysFont('segoeui', size, bold=bold)
    surf.blit(f.render(str(s), True, color), (int(x), int(y)))


def box(surf, rect, fill=PANEL, radius=16, border=BORDER):
    pygame.draw.rect(surf, fill, rect, border_radius=radius)
    pygame.draw.rect(surf, border, rect, 1, border_radius=radius)


def button(surf, rect, label, active=False, color=PURPLE):
    hover = rect.collidepoint(pygame.mouse.get_pos())
    box(surf, rect, color if active else (36, 50, 78) if hover else PANEL2, 11,
        color if active else BORDER)
    f = pygame.font.SysFont('segoeui', 17, bold=True)
    label_surface = f.render(label, True, (9, 16, 31) if active else WHITE)
    surf.blit(label_surface, label_surface.get_rect(center=rect.center))


def draw_grid(surf, rect, count=5):
    for i in range(1, count):
        yy = rect.y + int(rect.h * i / count)
        pygame.draw.line(surf, (40, 54, 81), (rect.x, yy), (rect.right, yy), 1)


def line_chart(surf, rect, samples, color, max_points=90):
    draw_grid(surf, rect)
    vals = [v for _, v in samples[-max_points:]]
    if len(vals) < 2:
        return
    maximum = max(4, max(vals) * 1.15)
    pts = [(rect.x + i * rect.w / (len(vals) - 1), rect.bottom - (v / maximum) * rect.h) for i, v in enumerate(vals)]
    pygame.draw.lines(surf, color, False, pts, 3)
    pygame.draw.circle(surf, color, (int(pts[-1][0]), int(pts[-1][1])), 5)


def draw_city(surf, sim):
    area = pygame.Rect(28, 180, 825, 604)
    box(surf, area, (11, 23, 42), 18)
    clip = surf.get_clip()
    surf.set_clip(area.inflate(-2, -2))
    # Urban blocks and decorative windows
    for row in range(4):
        for col in range(5):
            bx = 45 + col * 173
            by = 194 + row * 155
            if abs(bx + 70 - ROAD_X) < 125 or abs(by + 55 - ROAD_Y) < 125:
                continue
            pygame.draw.rect(surf, (19, 39, 62), (bx, by, 122, 107), border_radius=8)
            pygame.draw.rect(surf, (37, 68, 90), (bx+8, by+8, 106, 91), 1, border_radius=5)
            for xx in range(bx+20, bx+106, 22):
                for yy in range(by+20, by+94, 21):
                    pygame.draw.rect(surf, (39, 90, 111) if (xx + yy) % 3 else (58, 117, 132), (xx, yy, 7, 7), border_radius=1)
    pygame.draw.rect(surf, (32, 44, 64), (ROAD_X-ROAD_W//2, 180, ROAD_W, 604))
    pygame.draw.rect(surf, (32, 44, 64), (28, ROAD_Y-ROAD_W//2, 825, ROAD_W))
    # Lane dividers
    for yy in range(186, 780, 40):
        if abs(yy - ROAD_Y) > ROAD_W//2 + 5:
            pygame.draw.line(surf, (103, 120, 137), (ROAD_X, yy), (ROAD_X, yy+22), 2)
    for xx in range(35, 850, 40):
        if abs(xx - ROAD_X) > ROAD_W//2 + 5:
            pygame.draw.line(surf, (103, 120, 137), (xx, ROAD_Y), (xx+22, ROAD_Y), 2)
    pygame.draw.rect(surf, (39, 54, 76), (ROAD_X-ROAD_W//2, ROAD_Y-ROAD_W//2, ROAD_W, ROAD_W))
    # Zebra crossings
    for k in range(-3, 4):
        pygame.draw.rect(surf, (107, 125, 140), (ROAD_X + k*20 - 7, ROAD_Y-ROAD_W//2-21, 13, 12), border_radius=2)
        pygame.draw.rect(surf, (107, 125, 140), (ROAD_X + k*20 - 7, ROAD_Y+ROAD_W//2+9, 13, 12), border_radius=2)
        pygame.draw.rect(surf, (107, 125, 140), (ROAD_X-ROAD_W//2-21, ROAD_Y+k*20-7, 12, 13), border_radius=2)
        pygame.draw.rect(surf, (107, 125, 140), (ROAD_X+ROAD_W//2+9, ROAD_Y+k*20-7, 12, 13), border_radius=2)
    # Queued vehicles, four incoming directions
    for lane, queue in sim.queues.items():
        for idx, car in enumerate(list(queue)[:13]):
            dist = ROAD_W//2 + 34 + idx * 29
            if lane == 'N':
                r = pygame.Rect(ROAD_X+23, ROAD_Y-dist-22, 17, 25)
            elif lane == 'S':
                r = pygame.Rect(ROAD_X-41, ROAD_Y+dist, 17, 25)
            elif lane == 'W':
                r = pygame.Rect(ROAD_X-dist-24, ROAD_Y+22, 25, 17)
            else:
                r = pygame.Rect(ROAD_X+dist, ROAD_Y-39, 25, 17)
            pygame.draw.rect(surf, car.color, r, border_radius=4)
            pygame.draw.rect(surf, (8, 19, 32), r.inflate(-8, -8), border_radius=2)
    for lane, color, prog in sim.moving:
        if lane == 'N': r = pygame.Rect(ROAD_X+23, ROAD_Y-ROAD_W//2+prog, 17, 25)
        elif lane == 'S': r = pygame.Rect(ROAD_X-41, ROAD_Y+ROAD_W//2-prog, 17, 25)
        elif lane == 'W': r = pygame.Rect(ROAD_X-ROAD_W//2+prog, ROAD_Y+22, 25, 17)
        else: r = pygame.Rect(ROAD_X+ROAD_W//2-prog, ROAD_Y-39, 25, 17)
        pygame.draw.rect(surf, color, r, border_radius=4)
    # Signals: no green during yellow/all-red clearance
    clearance = sim.yellow_left > 0 or sim.clearance_left > 0
    for lane, cx, cy in [('N', ROAD_X+54, ROAD_Y-105), ('S', ROAD_X-55, ROAD_Y+105),
                         ('W', ROAD_X-105, ROAD_Y+53), ('E', ROAD_X+105, ROAD_Y-55)]:
        pygame.draw.circle(surf, (9, 15, 28), (cx, cy), 15)
        c = AMBER if sim.yellow_left > 0 else RED if clearance else GREEN if lane in sim.phase else RED
        pygame.draw.circle(surf, c, (cx, cy), 8)
    surf.set_clip(clip)
    text(surf, 'NORTH', 378, 193, 12, MUTED, True)
    text(surf, 'SOUTH', 378, 754, 12, MUTED, True)
    text(surf, 'WEST', 51, 414, 12, MUTED, True)
    text(surf, 'EAST', 792, 414, 12, MUTED, True)
    box(surf, pygame.Rect(48, 201, 225, 58), PANEL2, 10)
    text(surf, 'LIVE INTERSECTION', 64, 213, 13, CYAN, True)
    text(surf, f'{sim.mode.upper()} CONTROL', 64, 233, 14, WHITE, True)
    box(surf, pygame.Rect(618, 706, 210, 56), PANEL2, 10)
    text(surf, 'SIGNAL PHASE', 633, 715, 12, MUTED, True)
    status = 'ALL RED' if sim.clearance_left > 0 else 'YELLOW' if sim.yellow_left > 0 else ('N / S GREEN' if sim.phase == 'NS' else 'E / W GREEN')
    text(surf, status, 633, 733, 17, GREEN if 'GREEN' in status else AMBER if status == 'YELLOW' else RED, True)


def draw_panel(surf, sim, comparison, speed, paused, demand):
    x = 878
    box(surf, pygame.Rect(x, 180, 454, 604))
    text(surf, 'CONTROL CENTER', x+23, 201, 17, CYAN, True)
    text(surf, 'Switch between signal policies', x+23, 229, 14, MUTED)
    button(surf, pygame.Rect(x+22, 260, 193, 44), 'FIXED-TIME', sim.mode == 'Fixed-time')
    button(surf, pygame.Rect(x+235, 260, 194, 44), 'ADAPTIVE', sim.mode == 'Adaptive')
    pygame.draw.line(surf, BORDER, (x+22, 324), (x+432, 324))
    text(surf, 'SIMULATION TELEMETRY', x+22, 342, 15, MUTED, True)
    metrics = [('Vehicles served', str(sim.completed), CYAN),
               ('Waiting in queue', str(sim.total_queue()), AMBER),
               ('Mean served wait', f'{sim.avg_wait():.1f}s', GREEN),
               ('Elapsed time', f'{sim.time:.0f}s', PURPLE)]
    for i, (name, value, color) in enumerate(metrics):
        bx = x+22 + (i%2)*209
        by = 373 + (i//2)*96
        box(surf, pygame.Rect(bx, by, 195, 82), PANEL2, 10)
        text(surf, name, bx+12, by+12, 13, MUTED)
        text(surf, value, bx+12, by+34, 28, color, True)
    text(surf, 'TOTAL QUEUE · LAST 3 MINUTES', x+23, 578, 14, MUTED, True)
    line_chart(surf, pygame.Rect(x+25, 609, 398, 91), sim.queue_samples, CYAN)
    text(surf, f'Speed: {speed}x    |    Demand: {demand:.1f}x    |    {"PAUSED" if paused else "RUNNING"}', x+23, 730, 14, MUTED)
    text(surf, 'Press C for a reproducible policy experiment', x+23, 753, 12, PURPLE)


def draw_compare(surf, comparison, demand, seed):
    box(surf, pygame.Rect(28, 180, 1304, 604))
    text(surf, 'POLICY BENCHMARK', 55, 206, 27, WHITE, True)
    text(surf, 'Same seeded arrivals • 240 simulated seconds • two signal strategies', 55, 247, 16, MUTED)
    if comparison is None:
        text(surf, 'Press C to run the paired experiment.', 55, 305, 20, CYAN)
        return
    fixed, adaptive = comparison['Fixed-time'], comparison['Adaptive']
    for i, (label, sim, color) in enumerate([('FIXED-TIME', fixed, AMBER), ('ADAPTIVE', adaptive, GREEN)]):
        x = 58+i*641
        box(surf, pygame.Rect(x, 299, 606, 259), PANEL2)
        text(surf, label, x+22, 321, 20, color, True)
        for j, (name, val) in enumerate([('Vehicles served', str(sim.completed)), ('Mean served wait', f'{sim.avg_wait():.1f} s'),
                                          ('Remaining queue', str(sim.total_queue())), ('Longest served wait', f'{sim.wait_max:.1f} s')]):
            bx = x+22+(j%2)*290
            by = 365+(j//2)*85
            text(surf, name, bx, by, 15, MUTED)
            text(surf, val, bx, by+24, 29, WHITE, True)
    improvement = (fixed.avg_wait()-adaptive.avg_wait())/fixed.avg_wait()*100 if fixed.avg_wait() else 0
    text(surf, 'ADAPTIVE WAIT-TIME CHANGE', 58, 595, 16, MUTED, True)
    text(surf, f'{improvement:+.1f}% reduction vs fixed-time' if improvement >= 0 else f'{abs(improvement):.1f}% increase vs fixed-time',
         58, 624, 28, GREEN if improvement >= 0 else RED, True)
    text(surf, 'Synthetic stochastic experiment; results depend on demand, seed and policy parameters.', 58, 695, 15, MUTED)
    text(surf, f'Current experiment: seed {seed} | demand {demand:.1f}x | 0.1s numerical time step', 58, 725, 14, MUTED)


def export_csv(comparison, path):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['policy', 'arrived', 'served', 'remaining_queue', 'mean_served_wait_seconds', 'max_served_wait_seconds', 'signal_switches'])
        for name, sim in comparison.items():
            writer.writerow([name, sim.spawned, sim.completed, sim.total_queue(), round(sim.avg_wait(), 3), round(sim.wait_max, 3), sim.switches])


def main():
    pygame.init()
    pygame.display.set_caption('SmartCity AI | Traffic Intelligence Lab')
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    seed, demand, speed = 17, 1.0, 2
    sim = Simulation(seed, demand)
    comparison = None
    paused = False
    show_comparison = False
    notice, notice_until = '', 0
    buttons = {'fixed': pygame.Rect(900, 260, 193, 44), 'adaptive': pygame.Rect(1113, 260, 194, 44)}
    running = True
    while running:
        dt = min(clock.tick(FPS)/1000, 0.05)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: running = False
                elif event.key == pygame.K_SPACE: paused = not paused
                elif event.key == pygame.K_r:
                    sim = Simulation(seed, demand, sim.mode)
                    comparison = None
                elif event.key == pygame.K_f: sim = Simulation(seed, demand, 'Fixed-time')
                elif event.key == pygame.K_a: sim = Simulation(seed, demand, 'Adaptive')
                elif event.key == pygame.K_c:
                    comparison = compare(seed, demand)
                    show_comparison = not show_comparison if comparison is not None and show_comparison else True
                elif event.key == pygame.K_TAB: show_comparison = not show_comparison
                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS): speed = min(8, speed+1)
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS): speed = max(1, speed-1)
                elif event.key == pygame.K_UP:
                    demand = min(2.5, round(demand+0.2, 1)); sim = Simulation(seed, demand, sim.mode); comparison = None
                elif event.key == pygame.K_DOWN:
                    demand = max(0.4, round(demand-0.2, 1)); sim = Simulation(seed, demand, sim.mode); comparison = None
                elif event.key == pygame.K_s:
                    if comparison is None: comparison = compare(seed, demand)
                    output = Path(__file__).resolve().parent / 'benchmark_results.csv'
                    export_csv(comparison, output)
                    notice, notice_until = f'Saved: {output.name}', pygame.time.get_ticks()+3000
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not show_comparison:
                if buttons['fixed'].collidepoint(event.pos): sim = Simulation(seed, demand, 'Fixed-time')
                if buttons['adaptive'].collidepoint(event.pos): sim = Simulation(seed, demand, 'Adaptive')
        if not paused:
            for _ in range(speed): sim.step(dt)
        screen.fill(BG)
        pygame.draw.rect(screen, (14, 24, 44), (0, 0, WIDTH, 155))
        text(screen, 'SMARTCITY', 31, 22, 36, WHITE, True)
        text(screen, 'AI', 264, 22, 36, CYAN, True)
        text(screen, 'TRAFFIC INTELLIGENCE LAB  /  INTERACTIVE DIGITAL TWIN', 34, 69, 15, MUTED, True)
        box(screen, pygame.Rect(930, 25, 400, 58), PANEL2, 11)
        text(screen, '●  LIVE SIMULATION', 952, 42, 17, GREEN, True)
        text(screen, f'{speed}x', 1255, 42, 17, CYAN, True)
        text(screen, 'A Adaptive  •  F Fixed  •  C Compare  •  TAB View  •  SPACE Pause  •  R Reset', 32, 119, 15, MUTED)
        if show_comparison: draw_compare(screen, comparison, demand, seed)
        else:
            draw_city(screen, sim)
            draw_panel(screen, sim, comparison, speed, paused, demand)
        text(screen, '↑↓ DEMAND     +/- SPEED     S EXPORT CSV     ESC EXIT', 33, 801, 13, MUTED)
        text(screen, 'SYNTHETIC TRAFFIC • RULE-BASED CONTROL • NO MODEL TRAINING', 803, 801, 12, MUTED)
        if pygame.time.get_ticks() < notice_until:
            text(screen, notice, 530, 802, 14, GREEN, True)
        pygame.display.flip()
    pygame.quit()

if __name__ == '__main__':
    main()
