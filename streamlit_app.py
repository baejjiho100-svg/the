# -*- coding: utf-8 -*-
"""격자 카드게임 PvP - Streamlit 버전 (한 화면에서 번갈아 하는 hot-seat 방식)

실행:  streamlit run streamlit_app.py
배포:  grid_card_game.py, streamlit_app.py, requirements.txt 를 같은 폴더(GitHub 저장소)에 올리고
       Streamlit Community Cloud 에서 streamlit_app.py 를 메인 파일로 지정하면 됩니다.

게임 규칙과 카드 데이터는 grid_card_game.py(로직)에 있고, 이 파일은 화면만 담당합니다.
브라우저 세션마다 게임이 따로 만들어지며 서버에 파일을 저장하지 않습니다(덱은 세션 안에서만 유지).
"""
import streamlit as st

import grid_card_game as G

st.set_page_config(page_title="격자 카드게임 PvP", page_icon="🃏", layout="wide")

S = st.session_state
COLORS = ("#2457c5", "#c25a12")           # 플레이어 1 파랑 / 플레이어 2 주황
NAMES = ("플레이어 1(파랑)", "플레이어 2(주황)")


# ------------------------------------------------------------------ 상태 전환 (버튼 콜백)
def reset_all():
    S.mode = "build"                      # build -> pass -> game -> result -> pass ... -> over
    S.cur = 0                             # 지금 화면을 보는 플레이어
    S.decks = [dict(G.PRESET), dict(G.PRESET)]
    S.g = None
    S.msg = ""
    S.sel = None                          # 선택한 손패 번호
    S.aim_from = None                     # 조준 중인 내 원거리 카드 (행, 열)
    S.nxt = "build"


def go_pass(player, nxt):
    S.cur, S.mode, S.nxt = player, "pass", nxt
    S.sel, S.aim_from, S.msg = None, None, ""


def ready():
    S.mode = S.nxt
    S.msg = ""


def rebuild():
    S.mode, S.cur, S.g, S.msg, S.sel, S.aim_from = "build", 0, None, "", None, None


def start_game():
    S.g = G.Game([dict(d) for d in S.decks])
    go_pass(0, "game")


# ---- 덱 짜기
def tweak(k, delta):
    d = S.decks[S.cur]
    n = d.get(k, 0) + delta
    S.msg = ""
    if n < 0:
        return
    if n > G.COPY_MAX:
        S.msg = f"같은 카드는 {G.COPY_MAX}장까지예요."
    elif delta > 0 and G.deck_count(d) >= G.DECK_SIZE:
        S.msg = f"덱은 {G.DECK_SIZE}장이에요. 다른 카드를 먼저 빼세요."
    elif delta > 0 and G.deck_cost(d) + G.CARDS[k].cost > G.COST_CAP:
        S.msg = f"덱 코스트 한도 {G.COST_CAP}를 넘어요."
    else:
        d[k] = n


def random_fill_cb():
    d = S.decks[S.cur]
    G.random_fill(d)
    S.msg = "" if G.deck_count(d) >= G.DECK_SIZE else "남은 코스트로 채울 카드가 없어요. 비싼 카드를 하나 빼 보세요."


def clear_deck():
    S.decks[S.cur] = {}
    S.msg = ""


def confirm_deck():
    d = S.decks[S.cur]
    if not G.deck_ok(d):
        return
    S.decks[S.cur] = {k: n for k, n in d.items() if n}
    if S.cur == 0:
        go_pass(1, "build")
    else:
        start_game()


# ---- 게임 진행
def pick_hand(i):
    S.sel = None if S.sel == i else i
    S.aim_from = None
    S.msg = ""


def place(r, c):
    S.msg = S.g.play_unit(S.cur, S.sel, r, c)
    if not S.msg:
        S.sel = None


def cast(col):
    S.msg = S.g.cast_spell(S.cur, S.sel, col)
    if not S.msg:
        S.sel = None


def pick_aim(r, c):
    S.aim_from = None if S.aim_from == (r, c) else (r, c)
    S.sel = None
    S.msg = ""


def set_aim(target_row):
    ar, ac = S.aim_from
    S.msg = S.g.set_aim(S.cur, ar, ac, target_row)
    S.aim_from = None


def end_turn():
    if S.cur == 0:
        go_pass(1, "game")
    else:
        S.g.resolve()
        S.mode, S.sel, S.aim_from, S.msg = "result", None, None, ""


def next_round():
    S.g.finish_round()
    if S.g.over:
        S.mode = "over"
    else:
        go_pass(0, "game")


# ------------------------------------------------------------------ 화면 조각
def apply_theme(color, tight):
    css = f"""<style>
    .block-container{{border-top:8px solid {color};padding-top:1.2rem}}
    button[kind="primary"],button[data-testid="stBaseButton-primary"]{{background-color:{color};border-color:{color};color:#fff}}
    .stButton button{{line-height:1.15;white-space:normal}}
    """
    if tight:      # 보드는 좁은 화면에서도 5칸이 한 줄로 보이게
        css += """
    div[data-testid="stHorizontalBlock"]{flex-wrap:nowrap;gap:.3rem}
    div[data-testid="stColumn"],div[data-testid="column"]{min-width:0!important;flex:1 1 0!important}
    .stButton button{padding:.3rem .2rem;min-height:3rem;font-size:.8rem}
    """
    st.markdown(css + "</style>", unsafe_allow_html=True)


def icon_for(d):
    if d.special == "boom":
        return "💥"
    if d.special == "throw":
        return "🏗"
    if d.prod:
        return "⛏"
    return "🏹" if d.ranged else "⚔️"


def stat_text(d, hp):
    if d.prod:
        return f"+{d.prod}/{hp}"
    if d.special == "throw":
        return f"♥{hp}"
    return f"{d.atk}/{hp}"


def cell_label(u, grid, r, c, own, aimed=False):
    if u is None:
        return "🎯" if aimed else "·"
    if not own and u.fresh:
        return "❓뒤집힘"
    s = f"{icon_for(u.d)}{u.d.name} {stat_text(u.d, u.hp)}"
    if own and u.ranged and u.aim is not None:
        s += f" 🎯{G.ROW_NAMES[u.aim]}"
    if u.atk > 0 and not G.Game.can_attack(grid, r, c):
        s += " 💤"
    return ("🎯" + s) if aimed else s


def hand_label(h):
    if isinstance(h, G.Spell):
        return f"☄ {h.d.name} ({h.d.cost}) 즉발 {h.d.dmg}"
    return f"{icon_for(h.d)}{h.d.name} ({h.d.cost}) {stat_text(h.d, h.hp)}"


def board_rows(g):
    """전투 결과용 읽기 전용 표 (플레이어 1 시점)"""
    p0, p1 = g.players
    rows = []
    for r in (2, 1, 0):
        rows.append({"줄": f"2P {G.ROW_NAMES[r]}",
                     **{f"{c + 1}열": cell_label(p1.grid[r][c], p1.grid, r, c, False) for c in range(G.COLS)}})
    for r in range(G.ROWS):
        rows.append({"줄": f"1P {G.ROW_NAMES[r]}",
                     **{f"{c + 1}열": cell_label(p0.grid[r][c], p0.grid, r, c, False) for c in range(G.COLS)}})
    return rows


def hero_bar(p, label):
    st.progress(max(0.0, min(1.0, p.hp / G.HERO_HP)), text=f"{label} · 본체 {max(p.hp, 0)}/{G.HERO_HP}")


# ------------------------------------------------------------------ 화면
def build_screen():
    d = S.decks[S.cur]
    n, c = G.deck_count(d), G.deck_cost(d)
    st.subheader(f"● {NAMES[S.cur]}의 덱 짜기")
    st.caption(f"덱 {G.DECK_SIZE}장 · 같은 카드 최대 {G.COPY_MAX}장 · 덱 코스트 합계 {G.COST_CAP} 이하")
    a, b = st.columns(2)
    a.progress(min(1.0, n / G.DECK_SIZE), text=f"카드 수 {n}/{G.DECK_SIZE}")
    b.progress(min(1.0, c / G.COST_CAP), text=f"덱 코스트 {c}/{G.COST_CAP}")
    if S.msg:
        st.warning(S.msg)
    keys = sorted(G.CARDS, key=lambda k: (G.CARDS[k].cost, G.CARDS[k].name))
    for cost in sorted({G.CARDS[k].cost for k in keys}):
        st.markdown(f"**코스트 {cost}**")
        group = [k for k in keys if G.CARDS[k].cost == cost]
        cols = st.columns(3)
        for i, k in enumerate(group):
            cd, q = G.CARDS[k], d.get(k, 0)
            no_add = q >= G.COPY_MAX or n >= G.DECK_SIZE or c + cd.cost > G.COST_CAP
            with cols[i % 3]:
                with st.container(border=True):
                    kind = (f"⛏ 건물 · 매 턴 코스트 +{cd.prod}" if cd.prod
                            else "🏗 건물 · 매 턴 투석 카드 1장" if cd.special == "throw"
                            else f"{'🏹 원거리' if cd.ranged else '⚔️ 근접'} 공격 {cd.atk}" + (" · 💥 자폭" if cd.special == "boom" else ""))
                    st.markdown(f"**{cd.name}** {'✅' if q else ''}")
                    st.caption(f"{kind} · ♥{cd.hp}")
                    m, num, p = st.columns([1, 1, 1])
                    m.button("−", key=f"dm_{k}", on_click=tweak, args=(k, -1), disabled=q == 0, use_container_width=True)
                    num.markdown(f"<div style='text-align:center;padding-top:.4rem'><b>{q}</b></div>", unsafe_allow_html=True)
                    p.button("+", key=f"dp_{k}", on_click=tweak, args=(k, 1), disabled=no_add, use_container_width=True)
    x, y, z = st.columns(3)
    x.button("랜덤 채우기", on_click=random_fill_cb, use_container_width=True)
    y.button("비우기", on_click=clear_deck, use_container_width=True)
    z.button("덱 확정 (상대에게 넘기기)" if S.cur == 0 else "덱 확정 (게임 시작)", type="primary",
             on_click=confirm_deck, disabled=not G.deck_ok(d), use_container_width=True)


def pass_screen():
    if S.nxt == "build":
        text = f"{NAMES[S.cur]}이(가) 덱을 짤 차례예요."
    else:
        text = f"{NAMES[S.cur]} 차례예요. (턴 {S.g.turn})"
    st.markdown(f"## ● {text}")
    st.write("화면을 가리고 기기를 넘긴 뒤, 준비되면 아래 버튼을 누르세요. 상대의 손패는 보이지 않아요.")
    st.button("준비 완료", type="primary", on_click=ready)


def game_screen():
    g, v = S.g, S.cur
    me, foe = g.players[v], g.players[1 - v]
    sel_card = me.hand[S.sel] if S.sel is not None and S.sel < len(me.hand) else None
    spell_sel = isinstance(sel_card, G.Spell)
    unit_sel = sel_card is not None and not spell_sel
    aim = S.aim_from

    hero_bar(foe, f"● {foe.name} (상대) · 손패 {len(foe.hand)}장")
    for r in (2, 1, 0):                                   # 상대: 뒷줄이 위, 앞줄이 가운데 쪽
        cols = st.columns(G.COLS)
        for c in range(G.COLS):
            aimed = any(u is not None and u.ranged and u.aim == r for u in (me.grid[i][c] for i in range(G.ROWS)))
            cb, args = None, None
            if aim and aim[1] == c:
                cb, args = set_aim, (r,)
            elif spell_sel:
                cb, args = cast, (c,)
            cols[c].button(cell_label(foe.grid[r][c], foe.grid, r, c, False, aimed), key=f"foe_{r}_{c}",
                           on_click=cb, args=args, disabled=cb is None,
                           type="primary" if cb else "secondary", use_container_width=True)
    st.markdown("<div style='text-align:center;opacity:.6'>▲ 상대 · 나 ▼ (같은 열끼리 마주 봐요)</div>", unsafe_allow_html=True)
    for r in range(G.ROWS):
        cols = st.columns(G.COLS)
        for c in range(G.COLS):
            u = me.grid[r][c]
            cb, args, hot = None, None, False
            if unit_sel and u is None:
                cb, args, hot = place, (r, c), True
            elif u is not None and u.ranged and u.atk > 0:
                cb, args, hot = pick_aim, (r, c), aim == (r, c)
            cols[c].button(cell_label(u, me.grid, r, c, True), key=f"own_{r}_{c}",
                           on_click=cb, args=args, disabled=cb is None,
                           type="primary" if hot or (unit_sel and u is None) else "secondary",
                           use_container_width=True)
    hero_bar(me, f"● {me.name} (나)")

    extra = (f" (이월 +{me.carry}" if me.carry else "") + (f"{',' if me.carry else ' ('} 건물 +{me.prod}" if me.prod else "")
    extra += ")" if extra else ""
    st.markdown(f"**턴 {g.turn}** · 코스트 **{me.left}/{me.cap}**{extra} · 덱 {len(me.deck)}장")
    if me.orders:
        st.caption("예약한 즉발: " + ", ".join(f"{n}→{c + 1}열" for n, c, _ in me.orders))
    if S.msg:
        st.warning(S.msg)
    if aim:
        st.info("같은 열에서 노릴 상대 카드를 누르세요. 앞줄 100% · 중간줄 75% · 뒷줄 50% 피해, 같은 줄을 다시 누르면 자동 조준이에요.")
    elif spell_sel:
        st.info("상대 보드에서 노릴 열을 누르세요. 그 열의 맨 앞 카드가 맞아요.")
    elif unit_sel:
        st.info("내 보드의 빈 칸을 눌러 카드를 놓으세요.")
    else:
        st.caption("손패에서 카드를 고르세요. 내 원거리 카드를 누르면 조준 대상을 정할 수 있어요. 💤 = 공격 대기")

    for start in range(0, max(len(me.hand), 1), 4):
        chunk = me.hand[start:start + 4]
        cols = st.columns(4)
        for j, h in enumerate(chunk):
            i = start + j
            cols[j].button(hand_label(h), key=f"hand_{i}", on_click=pick_hand, args=(i,),
                           disabled=h.d.cost > me.left, type="primary" if S.sel == i else "secondary",
                           use_container_width=True)
    if not me.hand:
        st.caption("손패가 비었어요. 다음 턴에 카드가 채워져요.")
    st.button("턴 종료 (상대에게 넘기기)" if v == 0 else "턴 종료 (전투 시작)", type="primary", on_click=end_turn)


def result_screen():
    g = S.g
    st.subheader(f"턴 {g.turn} 전투 결과")
    st.dataframe(board_rows(g), hide_index=True, use_container_width=True)
    for line in g.events:
        st.write("• " + line)
    p0, p1 = g.players
    st.write(f"본체 체력 — {p0.name} {max(p0.hp, 0)}/{G.HERO_HP} · {p1.name} {max(p1.hp, 0)}/{G.HERO_HP}")
    st.button("다음 턴으로", type="primary", on_click=next_round)


def over_screen():
    g = S.g
    st.subheader("게임 종료")
    st.success(g.result)
    st.dataframe(board_rows(g), hide_index=True, use_container_width=True)
    for line in g.events:
        st.write("• " + line)
    a, b = st.columns(2)
    a.button("같은 덱으로 다시", type="primary", on_click=start_game, use_container_width=True)
    b.button("덱 다시 짜기", on_click=rebuild, use_container_width=True)


def sidebar():
    with st.sidebar:
        st.header("🃏 격자 카드게임")
        with st.expander("규칙 보기", expanded=False):
            st.markdown(
                f"""
- 각자 5x3 격자, 같은 열끼리 마주 봐요. 덱은 {G.DECK_SIZE}장(같은 카드 {G.COPY_MAX}장까지, 덱 코스트 {G.COST_CAP} 이하).
- 코스트는 턴마다 +1(기본 최대 8). 남긴 코스트는 {G.CARRY_MAX}까지 이월, 건물 생산분은 따로 더해져요.
- 손패는 매 턴 {G.HAND_FILL}장까지 채워져요(최소 1장).
- 전투는 두 플레이어 동시에: 즉발 → 근접 전진 → 공격 → 사망 처리.
- ⚔️ 근접: 같은 열 맨 앞 적을 공격, 자기 열의 맨 앞일 때만 공격, 앞이 비면 전진(전진한 턴은 공격 못 함).
- 🏹 원거리: 뒤에서도 공격, 같은 열에서 대상을 고를 수 있어요(앞 100% · 중 75% · 뒤 50% 피해).
- 열에 적 카드가 없으면 본체를 직접 공격해요. 본체 체력은 {G.HERO_HP}.
- ⛏ 건물은 코스트를 만들고, 🏗 투석기는 매 턴 투석(☄ 즉발) 카드를 만들어요. 💥 자폭병은 공격하면서 폭발해요.
"""
            )
        if S.mode in ("game", "result", "pass") and S.g is not None:
            st.button("덱 다시 짜기 (현재 판 포기)", on_click=rebuild)
        st.button("완전 초기화", on_click=reset_all)


# ------------------------------------------------------------------ 진입점
if "mode" not in S:
    reset_all()

_color = "#555555" if S.mode in ("result", "over") else COLORS[S.cur]
apply_theme(_color, tight=S.mode in ("game", "result", "over"))
st.title("격자 카드게임 PvP")
sidebar()
{"build": build_screen, "pass": pass_screen, "game": game_screen,
 "result": result_screen, "over": over_screen}[S.mode]()
