#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""격자 카드게임 PvP (한 컴퓨터에서 번갈아 플레이) - 파이썬 버전

구조
  1) 데이터 : CARDS, SPELLS            (카드 정의, 나중에 JSON으로 빼기 쉬움)
  2) 로직   : Player, Game             (화면과 무관, 웹/GUI에서 그대로 재사용 가능)
  3) 화면   : show_board, build_deck, play_phase, main   (터미널 UI)

규칙 요약
  - 각자 5x3 격자(행 0 = 앞줄). 같은 열끼리 마주 본다.
  - 덱 16장, 같은 카드 최대 3장, 덱 코스트 합계 34 이하.
  - 코스트: 턴마다 +1 (최대 8), 남긴 코스트는 2까지 이월, 건물 생산분은 따로 더해짐.
  - 손패는 매 턴 4장까지 채워짐(최소 1장). 투석 카드는 장수에 포함되지 않음.
  - 전투(두 플레이어 동시 처리): 즉발 카드 -> 근접 전진 -> 공격 -> 사망 처리.
  - 근접: 열의 맨 앞 적을 공격, 자기 열의 맨 앞일 때만 공격, 앞이 비면 전진(전진한 턴은 공격 못 함).
  - 원거리: 뒤에서도 공격, 같은 열에서 대상을 고를 수 있음(앞 100% / 중 75% / 뒤 50% 피해).
  - 열에 적 카드가 없으면 본체를 직접 공격.
"""
from __future__ import annotations

import json
import os
import random
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

# ------------------------------------------------------------------ 설정
ROWS, COLS = 3, 5
HERO_HP = 20
HAND_START, HAND_FILL = 4, 4
DECK_SIZE, COPY_MAX, COST_CAP = 16, 3, 34
CARRY_MAX, MANA_CAP = 2, 10
FALLOFF = (1.0, 0.75, 0.5)          # 원거리: 맞는 줄(앞/중/뒤)별 피해 배율
ROW_NAMES = ("앞", "중", "뒤")


# ------------------------------------------------------------------ 카드 데이터
@dataclass(frozen=True)
class CardDef:
    name: str
    cost: int
    atk: int
    hp: int
    prod: int = 0            # 매 턴 코스트 생산량 (건물)
    ranged: bool = False
    special: str = ""        # "boom" 자폭 / "throw" 매 턴 투석 카드 생산


@dataclass(frozen=True)
class SpellDef:
    name: str
    cost: int
    dmg: int


# 스탯 예산: 근접 = 3*코스트+5, 원거리 = 3*코스트+1 (점수 = 공격*2 + 체력)
CARDS: dict[str, CardDef] = {
    "soldier":   CardDef("병사", 1, 2, 4),
    "shield":    CardDef("방패병", 1, 1, 6),
    "sling":     CardDef("투석병", 1, 1, 2, ranged=True),
    "knight":    CardDef("기사", 2, 3, 5),
    "guard":     CardDef("수호병", 2, 1, 9),
    "charger":   CardDef("돌격병", 2, 4, 3),
    "archer":    CardDef("궁수", 2, 2, 3, ranged=True),
    "bomber":    CardDef("자폭병", 2, 6, 2, special="boom"),
    "mine":      CardDef("광산", 2, 0, 6, prod=1),
    "berserker": CardDef("광전사", 3, 5, 4),
    "mage":      CardDef("마법사", 3, 3, 4, ranged=True),
    "catapult":  CardDef("투석기", 3, 0, 6, special="throw"),
    "golem":     CardDef("골렘", 4, 3, 11),
    "sniper":    CardDef("저격수", 4, 5, 3, ranged=True),
    "tower":     CardDef("수정탑", 4, 0, 8, prod=2),
    "giant":     CardDef("거인", 5, 4, 12),
    "champion":  CardDef("용사", 5, 7, 6),
    "cannon":    CardDef("포병", 5, 6, 4, ranged=True),
}
SPELLS = {"throw": SpellDef("투석", 1, 3)}      # 투석기에서만 나오는 즉발 카드
PRESET = {"soldier": 3, "shield": 2, "sling": 2, "knight": 3,
          "guard": 1, "archer": 3, "mage": 1, "golem": 1}


# ------------------------------------------------------------------ 덱 규칙
def deck_count(d: dict[str, int]) -> int:
    return sum(d.values())


def deck_cost(d: dict[str, int]) -> int:
    return sum(CARDS[k].cost * n for k, n in d.items() if k in CARDS)


def deck_ok(d) -> bool:
    return (isinstance(d, dict) and deck_count(d) == DECK_SIZE and deck_cost(d) <= COST_CAP
            and all(k in CARDS and isinstance(n, int) and 0 <= n <= COPY_MAX for k, n in d.items()))


def random_fill(d: dict[str, int]) -> None:
    while deck_count(d) < DECK_SIZE:
        options = [k for k, c in CARDS.items()
                   if d.get(k, 0) < COPY_MAX and deck_cost(d) + c.cost <= COST_CAP]
        if not options:
            break
        k = random.choice(options)
        d[k] = d.get(k, 0) + 1


DECK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "decks.json")


def load_decks() -> list[dict[str, int]]:
    try:
        with open(DECK_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) == 2 and all(deck_ok(d) for d in data):
            return data
    except (OSError, ValueError):
        pass
    return [dict(PRESET), dict(PRESET)]


def save_decks(decks) -> None:
    try:
        with open(DECK_FILE, "w", encoding="utf-8") as f:
            json.dump(decks, f, ensure_ascii=False)
    except OSError:
        pass


# ------------------------------------------------------------------ 로직
@dataclass
class Unit:
    key: str
    hp: int
    aim: Optional[int] = None      # 원거리 조준 줄(0~2), None = 자동(맨 앞)
    fresh: bool = False            # 이번 턴에 놓음 (상대에게는 뒤집힌 카드)
    moved: bool = False            # 이번 전투에서 전진함 (공격 못 함)

    @property
    def d(self) -> CardDef:
        return CARDS[self.key]

    @property
    def atk(self) -> int:
        return self.d.atk

    @property
    def ranged(self) -> bool:
        return self.d.ranged


@dataclass
class Spell:
    key: str

    @property
    def d(self) -> SpellDef:
        return SPELLS[self.key]


def new_unit(key: str) -> Unit:
    return Unit(key, CARDS[key].hp)


@dataclass
class Player:
    name: str
    deck: list[str]
    hand: list = field(default_factory=list)
    grid: list = field(default_factory=lambda: [[None] * COLS for _ in range(ROWS)])
    hp: int = HERO_HP
    left: int = 0
    cap: int = 0
    carry: int = 0
    prod: int = 0
    orders: list = field(default_factory=list)     # 예약한 즉발: (이름, 열, 피해)

    def units(self):
        for r in range(ROWS):
            for c in range(COLS):
                if self.grid[r][c] is not None:
                    yield r, c, self.grid[r][c]

    def draw(self, n: int) -> None:
        for _ in range(n):
            if self.deck:
                self.hand.append(new_unit(self.deck.pop()))

    def refill(self) -> None:
        in_hand = sum(isinstance(h, Unit) for h in self.hand)
        self.draw(max(1, HAND_FILL - in_hand))


def mana_for(turn: int) -> int:
    return min(turn + 2, 8)


class Game:
    def __init__(self, decks: list[dict[str, int]]):
        names = ("플레이어 1(파랑)", "플레이어 2(주황)")
        self.players: list[Player] = []
        for name, counts in zip(names, decks):
            cards = [k for k, n in counts.items() for _ in range(n)]
            random.shuffle(cards)
            self.players.append(Player(name, cards))
        for p in self.players:
            p.draw(HAND_START)
        self.turn = 1
        self.over = False
        self.result = ""
        self.events: list[str] = []      # 직전 전투 기록
        self._start_turn_mana()

    # ---- 코스트
    def _start_turn_mana(self) -> None:
        for p in self.players:
            p.prod = sum(u.d.prod for _, _, u in p.units())
            p.cap = min(MANA_CAP, mana_for(self.turn) + p.carry) + p.prod
            p.left = p.cap

    # ---- 규칙 판정
    @staticmethod
    def can_attack(grid, r: int, c: int) -> bool:
        u = grid[r][c]
        if u is None or u.atk <= 0:
            return False
        if u.ranged:
            return True
        return not any(grid[i][c] is not None and grid[i][c].atk > 0 for i in range(r))

    @staticmethod
    def pick_target(col: int, grid):
        for r in range(ROWS):
            if grid[r][col] is not None:
                return r, col
        return None

    def aim_target(self, u: Unit, col: int, grid):
        if u.ranged and u.aim is not None and grid[u.aim][col] is not None:
            return u.aim, col
        return self.pick_target(col, grid)

    @staticmethod
    def damage_for(u: Unit, target_row: int) -> int:
        if u.ranged:
            return max(1, int(u.atk * FALLOFF[target_row]))
        return u.atk

    # ---- 플레이어 행동 (오류 문자열을 돌려주고, 성공하면 "")
    def play_unit(self, pi: int, hand_idx: int, row: int, col: int) -> str:
        p = self.players[pi]
        if not 0 <= hand_idx < len(p.hand):
            return "그런 손패 번호가 없어요."
        card = p.hand[hand_idx]
        if not isinstance(card, Unit):
            return "즉발 카드는 s 명령으로 쓰세요."
        if not (0 <= row < ROWS and 0 <= col < COLS):
            return "행은 1~3, 열은 1~5예요."
        if p.grid[row][col] is not None:
            return "이미 카드가 있는 칸이에요."
        if card.d.cost > p.left:
            return "코스트가 부족해요."
        card.fresh = True
        p.grid[row][col] = card
        p.hand.pop(hand_idx)
        p.left -= card.d.cost
        return ""

    def cast_spell(self, pi: int, hand_idx: int, col: int) -> str:
        p = self.players[pi]
        if not 0 <= hand_idx < len(p.hand):
            return "그런 손패 번호가 없어요."
        card = p.hand[hand_idx]
        if not isinstance(card, Spell):
            return "이 카드는 p 명령으로 보드에 놓으세요."
        if not 0 <= col < COLS:
            return "열은 1~5예요."
        if card.d.cost > p.left:
            return "코스트가 부족해요."
        p.orders.append((card.d.name, col, card.d.dmg))
        p.hand.pop(hand_idx)
        p.left -= card.d.cost
        return ""

    def set_aim(self, pi: int, row: int, col: int, target_row: int) -> str:
        """내 (row, col) 원거리 카드의 조준 줄을 바꾼다. target_row=-1 이면 자동, 같은 줄을 다시 지정하면 해제."""
        p = self.players[pi]
        if not (0 <= row < ROWS and 0 <= col < COLS) or p.grid[row][col] is None:
            return "그 칸에 카드가 없어요."
        u = p.grid[row][col]
        if not (u.ranged and u.atk > 0):
            return "원거리 카드만 조준할 수 있어요."
        if target_row not in (-1, 0, 1, 2):
            return "상대 줄은 1(앞)~3(뒤), 자동은 0이에요."
        u.aim = None if target_row == -1 or u.aim == target_row else target_row
        return ""

    # ---- 전투 (두 플레이어 동시 처리)
    def _sweep(self, clear_flags: bool):
        dead, lost = 0, [0, 0]
        for i, p in enumerate(self.players):
            for r, c, u in list(p.units()):
                if clear_flags:
                    u.fresh = False
                    u.moved = False
                if u.hp <= 0:
                    p.grid[r][c] = None
                    dead += 1
                    if u.atk == 0:
                        lost[i] += 1
        return dead, lost

    def _cast_orders(self) -> None:
        hit, n = [], 0
        for a, p in enumerate(self.players):
            for name, col, dmg in p.orders:
                n += 1
                t = self.pick_target(col, self.players[1 - a].grid)
                if t:
                    hit.append((1 - a, t, dmg))
                else:
                    self.events.append(f"{p.name}의 {name}: {col + 1}열에 대상이 없어 불발")
            p.orders = []
        for d, (r, c), dmg in hit:
            self.players[d].grid[r][c].hp -= dmg
        dead, _ = self._sweep(False)
        if n:
            self.events.append(f"즉발 {n}회 발동" + (f", 쓰러진 카드 {dead}장" if dead else ""))

    def _advance(self) -> int:
        moved = 0
        for p in self.players:
            for c in range(COLS):
                for r in range(1, ROWS):
                    u = p.grid[r][c]
                    if u is not None and not u.ranged and u.atk > 0 and p.grid[r - 1][c] is None:
                        p.grid[r - 1][c], p.grid[r][c] = u, None
                        u.moved = True
                        moved += 1
        return moved

    def resolve(self) -> None:
        self.events = []
        self._cast_orders()
        moved = self._advance()
        hits: list[list] = [[], []]
        hero = [0, 0]
        booms: list[Unit] = []
        for a in (0, 1):
            d = 1 - a
            mine, foe = self.players[a].grid, self.players[d].grid
            for r in range(ROWS):
                for c in range(COLS):
                    u = mine[r][c]
                    if u is None or u.moved or not self.can_attack(mine, r, c):
                        continue
                    t = self.aim_target(u, c, foe)
                    if t:
                        hits[d].append((t, self.damage_for(u, t[0])))
                    else:
                        hero[d] += u.atk
                    if u.d.special == "boom":                 # 양옆 열 맨 앞 카드에 절반 피해
                        for cc in (c - 1, c + 1):
                            if 0 <= cc < COLS:
                                v = self.pick_target(cc, foe)
                                if v:
                                    hits[d].append((v, u.atk // 2))
                        booms.append(u)
        for d in (0, 1):
            for (r, c), n in hits[d]:
                self.players[d].grid[r][c].hp -= n
        for b in booms:
            b.hp = 0
        dead, lost = self._sweep(True)
        for d in (0, 1):
            self.players[d].hp -= hero[d]
        msg = (f"턴 {self.turn}: 근접 이동 {moved}회, 자폭 {len(booms)}회, 쓰러진 카드 {dead}장 | "
               f"본체 피해 {self.players[0].name} -{hero[0]}, {self.players[1].name} -{hero[1]}")
        if sum(lost):
            msg += f" | 건물 파괴 1P {lost[0]}채, 2P {lost[1]}채"
        self.events.append(msg)

    def finish_round(self) -> None:
        """전투 뒤 호출: 승패 확인 -> 코스트 이월 -> 다음 턴 준비(보충, 투석 생산)."""
        d0, d1 = (p.hp <= 0 for p in self.players)
        if d0 or d1:
            self.over = True
            self.result = "무승부" if d0 and d1 else (f"{self.players[0].name} 승리!" if d1
                                                     else f"{self.players[1].name} 승리!")
            return
        for p in self.players:
            p.carry = min(p.left, CARRY_MAX)
        self.turn += 1
        self._start_turn_mana()
        for p in self.players:
            p.refill()
            p.hand += [Spell("throw") for _, _, u in p.units() if u.d.special == "throw"]

    # ---- 웹/네트워크용: 한 플레이어 시점의 상태 (상대 손패와 이번 턴 카드는 숨김)
    def view_state(self, viewer: int) -> dict:
        def cell(u, own):
            if u is None:
                return None
            if not own and u.fresh:
                return {"hidden": True}
            return {"key": u.key, "name": u.d.name, "atk": u.atk, "hp": u.hp,
                    "ranged": u.ranged, "aim": u.aim if own else None}
        me, foe = self.players[viewer], self.players[1 - viewer]
        return {
            "turn": self.turn, "over": self.over, "result": self.result,
            "me": {"hp": me.hp, "left": me.left, "cap": me.cap, "deck": len(me.deck),
                   "hand": [{"name": h.d.name, "cost": h.d.cost} for h in me.hand],
                   "grid": [[cell(u, True) for u in row] for row in me.grid]},
            "foe": {"hp": foe.hp, "hand": len(foe.hand),
                    "grid": [[cell(u, False) for u in row] for row in foe.grid]},
        }


# ------------------------------------------------------------------ 터미널 화면
HELP = """명령어
  p 손패 행 열     카드를 내 보드에 놓기   (행 1=앞줄~3=뒷줄, 열 1~5)   예) p 1 1 3
  s 손패 열        즉발 카드(투석) 쓰기: 상대 그 열의 맨 앞 카드 공격   예) s 2 4
  a 행 열 상대행   내 원거리 카드의 조준 줄 지정 (상대 1=앞 2=중 3=뒤, 0=자동, 같은 줄 다시 지정=해제)
  e                턴 종료    q  게임 종료
표시: ·=빈 칸  ????=상대가 이번 턴에 놓은 카드  ~=공격 대기  *=내가 조준한 칸  !=자폭  >뒤=조준 중"""


def clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def wlen(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def pad(s: str, w: int) -> str:
    return s + " " * max(0, w - wlen(s))


def cell_text(u, grid, r, c, own: bool) -> str:
    if u is None:
        return "·"
    if not own and u.fresh:
        return "????"
    d = u.d
    if d.prod:
        s = f"{d.name} +{d.prod}/{u.hp}"
    elif d.special == "throw":
        s = f"{d.name} 생산/{u.hp}"
    else:
        s = f"{d.name}{'·원' if d.ranged else ''} {u.atk}/{u.hp}"
    if d.special == "boom":
        s += "!"
    if own and u.ranged and u.aim is not None:
        s += f">{ROW_NAMES[u.aim]}"
    if u.atk > 0 and not Game.can_attack(grid, r, c):
        s += "~"
    return s


def show_board(g: Game, viewer: int) -> None:
    me, foe = g.players[viewer], g.players[1 - viewer]
    cw = 16
    print(pad("", 7) + "".join(pad(f"  {c + 1}열", cw + 1) for c in range(COLS)))
    print(f"[{foe.name}] 본체 {foe.hp}/{HERO_HP}   손패 {len(foe.hand)}장")
    for r in (2, 1, 0):                                  # 상대는 뒷줄이 위, 앞줄이 가운데 쪽
        cells = []
        for c in range(COLS):
            aimed = any(u is not None and u.ranged and u.aim == r for u in (me.grid[i][c] for i in range(ROWS)))
            cells.append(pad(("*" if aimed else "") + cell_text(foe.grid[r][c], foe.grid, r, c, False), cw))
        print(f"  {ROW_NAMES[r]}줄 |" + "|".join(cells) + "|")
    print("  " + "-" * (7 + (cw + 1) * COLS) + "  ▲ 상대 / 나 ▼")
    for r in range(ROWS):
        cells = [pad(cell_text(me.grid[r][c], me.grid, r, c, True), cw) for c in range(COLS)]
        print(f"  {ROW_NAMES[r]}줄 |" + "|".join(cells) + "|")
    print(f"[{me.name}] 본체 {me.hp}/{HERO_HP}")


def hand_line(i: int, h) -> str:
    d = h.d
    if isinstance(h, Spell):
        return f"  [{i}] {d.name}  코스트 {d.cost}  즉발: 고른 열의 맨 앞 적에게 피해 {d.dmg}"
    if d.prod:
        kind = f"건물, 매 턴 코스트 +{d.prod}, 체력 {h.hp}"
    elif d.special == "throw":
        kind = f"건물, 매 턴 투석 카드 1장, 체력 {h.hp}"
    else:
        kind = f"{'원거리' if d.ranged else '근접'} 공격 {d.atk} 체력 {h.hp}" + (" (자폭)" if d.special == "boom" else "")
    return f"  [{i}] {d.name}  코스트 {d.cost}  {kind}"


def handoff(text: str) -> None:
    clear()
    input(f"\n{text}\n기기를 넘기고 준비되면 Enter를 누르세요...")


def build_deck(deck: dict[str, int], name: str) -> dict[str, int]:
    deck = dict(deck)
    keys = sorted(CARDS, key=lambda k: (CARDS[k].cost, CARDS[k].name))
    msg = ""
    while True:
        clear()
        print(f"=== {name} 덱 짜기 ===  카드 {deck_count(deck)}/{DECK_SIZE}   덱 코스트 {deck_cost(deck)}/{COST_CAP}"
              f"   (같은 카드 최대 {COPY_MAX}장)")
        for i, k in enumerate(keys, 1):
            c = CARDS[k]
            info = (f"건물 +{c.prod}코스트" if c.prod else "건물 투석 카드 생산" if c.special == "throw"
                    else f"{'원거리' if c.ranged else '근접'} {c.atk}")
            print(f"  [{i:2}] {pad(c.name, 8)} 코스트 {c.cost}  {pad(info, 20)} 체력 {c.hp:2}   x {deck.get(k, 0)}")
        print("\n  + 번호 / - 번호 : 카드 추가·제거   r : 랜덤으로 채우기   c : 비우기   ok : 확정")
        if msg:
            print("\n" + msg)
        parts = input("덱> ").strip().split()
        msg = ""
        if not parts:
            continue
        try:
            if parts[0] in ("+", "-") and len(parts) == 2:
                k = keys[int(parts[1]) - 1]
                n = deck.get(k, 0) + (1 if parts[0] == "+" else -1)
                if n < 0:
                    continue
                if n > COPY_MAX:
                    msg = f"같은 카드는 {COPY_MAX}장까지예요."
                elif parts[0] == "+" and deck_count(deck) >= DECK_SIZE:
                    msg = f"덱은 {DECK_SIZE}장이에요. 다른 카드를 먼저 빼세요."
                elif parts[0] == "+" and deck_cost(deck) + CARDS[k].cost > COST_CAP:
                    msg = f"덱 코스트 한도 {COST_CAP}를 넘어요."
                else:
                    deck[k] = n
            elif parts[0] == "r":
                random_fill(deck)
            elif parts[0] == "c":
                deck = {}
            elif parts[0] == "ok":
                if deck_ok(deck):
                    return {k: n for k, n in deck.items() if n}
                msg = f"카드 {DECK_SIZE}장, 덱 코스트 {COST_CAP} 이하로 맞춰 주세요."
        except (ValueError, IndexError):
            msg = "번호를 확인하세요."


def play_phase(g: Game, pi: int) -> None:
    me = g.players[pi]
    msg = ""
    while True:
        clear()
        print(f"=== {me.name} 차례 · 턴 {g.turn} ===")
        show_board(g, pi)
        extra = (f" (이월 +{me.carry}" if me.carry else " (") + (f", 건물 +{me.prod})" if me.prod else ")")
        extra = extra if extra not in (" ()", " (") else ""
        print(f"\n코스트 {me.left}/{me.cap}{extra}   덱 {len(me.deck)}장")
        if me.orders:
            print("예약한 즉발: " + ", ".join(f"{n}→{c + 1}열" for n, c, _ in me.orders))
        print("손패")
        print("\n".join(hand_line(i, h) for i, h in enumerate(me.hand, 1)) or "  (비었어요. 다음 턴에 채워져요)")
        if msg:
            print("\n" + msg)
        parts = input("\n명령(?=도움말)> ").strip().split()
        msg = ""
        if not parts:
            continue
        k = parts[0].lower()
        try:
            if k == "e":
                return
            if k == "q":
                raise SystemExit
            if k == "p" and len(parts) == 4:
                msg = g.play_unit(pi, int(parts[1]) - 1, int(parts[2]) - 1, int(parts[3]) - 1)
            elif k == "s" and len(parts) == 3:
                msg = g.cast_spell(pi, int(parts[1]) - 1, int(parts[2]) - 1)
            elif k == "a" and len(parts) == 4:
                msg = g.set_aim(pi, int(parts[1]) - 1, int(parts[2]) - 1, int(parts[3]) - 1)
            else:
                msg = HELP
        except ValueError:
            msg = "숫자로 입력하세요.\n" + HELP


def main() -> None:
    decks = load_decks()
    names = ("플레이어 1(파랑)", "플레이어 2(주황)")
    for i in (0, 1):
        handoff(f"{names[i]}이(가) 덱을 짤 차례예요.")
        decks[i] = build_deck(decks[i], names[i])
    save_decks(decks)
    g = Game(decks)
    while not g.over:
        for pi in (0, 1):
            handoff(f"{g.players[pi].name} 차례예요. (턴 {g.turn})")
            play_phase(g, pi)
        g.resolve()
        clear()
        print(f"=== 턴 {g.turn} 전투 결과 ===")
        show_board(g, 0)
        print("\n" + "\n".join(g.events))
        input("\nEnter를 누르면 계속...")
        g.finish_round()
    print(f"\n*** {g.result} ***")


if __name__ == "__main__":
    main()
