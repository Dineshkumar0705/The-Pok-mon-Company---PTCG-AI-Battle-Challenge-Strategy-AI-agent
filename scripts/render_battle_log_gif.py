#!/usr/bin/env python3
"""Generates a real, authentic battle-log GIF for the README: runs ONE real
self-play game through the actual `cg` engine (this project's own real
agent on both seats) and renders the engine's own real event log
(`Observation.logs` -- TURN_START, ATTACK, HP_CHANGE, PLAY, ATTACH, EVOLVE,
RESULT, etc., see vendor/cg/api.py's LogType) as a scrolling terminal-style
GIF. Every card name, attack name, and damage number in the GIF is real
data read off this real game -- nothing scripted or invented, no character
artwork (just text, same as every other place this project cites real card
names).

Usage:
    python3 scripts/render_battle_log_gif.py --out docs/assets/battle_log.gif
"""
from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (REPO_ROOT, os.path.join(REPO_ROOT, "src"), os.path.join(REPO_ROOT, "vendor")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

MAX_STEPS = 400


def _load_deck_file(path: str) -> list[int]:
    return [int(x) for x in open(path).read().split() if x.strip()]


def _play_and_collect_lines(deck: list[int], card_table: dict, attack_table: dict) -> list[str]:
    from cg import game
    from pokemon_agent.agent import build_agent

    agent = build_agent(deck)
    lines: list[str] = []

    def cname(cid):
        c = card_table.get(cid)
        return c.name if c else f"Card#{cid}"

    def aname(aid):
        a = attack_table.get(aid)
        return a.name if a else f"Attack#{aid}"

    def pflag(p):
        return "P1" if p == 0 else "P2"

    # Collected as (turn, player, action_lines) BLOCKS first, not flattened
    # text, so a real engine quirk can be handled honestly: this engine can
    # emit a second real TURN_START (and replay an identical opening action
    # sequence) before State.turn actually advances -- observed directly in
    # real self-play, most consistent with a mulligan/redraw retry (no
    # Basic Pokemon in the opening hand, a real TCG rule). Rather than guess
    # at the exact cause, blocks whose action lines are BYTE-IDENTICAL to
    # the immediately preceding block are collapsed to one (keeping the
    # LAST real turn number shown for it) after the game finishes -- a
    # real, visible game is what ships, not a doubled replay of one retry.
    blocks: list[dict] = []

    def new_block(turn, player):
        blocks.append({"turn": turn, "player": player, "actions": []})

    def cur_actions():
        return blocks[-1]["actions"] if blocks else None

    result_lines: list[str] = []

    obs_dict, _start = game.battle_start(deck, deck)
    try:
        for _ in range(1, MAX_STEPS + 1):
            sel = obs_dict.get("select")
            if sel is None:
                break
            result = obs_dict.get("current", {}).get("result", -1)
            if result != -1:
                break

            real_turn = obs_dict.get("current", {}).get("turn")
            for log in obs_dict.get("logs", []):
                t = log.get("type")
                p = log.get("playerIndex")
                if t == 2:  # TURN_START
                    new_block(real_turn, p)
                elif t == 10 and cur_actions() is not None:  # PLAY
                    cur_actions().append(f"  {pflag(p)} plays {cname(log['cardId'])}")
                elif t == 11 and cur_actions() is not None:  # ATTACH
                    cur_actions().append(f"  {pflag(p)} attaches {cname(log['cardId'])} -> {cname(log['cardIdTarget'])}")
                elif t == 12 and cur_actions() is not None:  # EVOLVE
                    cur_actions().append(f"  {pflag(p)} evolves {cname(log['cardIdTarget'])} -> {cname(log['cardId'])}!")
                elif t == 15 and cur_actions() is not None:  # ATTACK
                    cur_actions().append(f"  >> {pflag(p)}'s {cname(log['cardId'])} uses {aname(log['attackId'])}!")
                elif t == 16 and cur_actions() is not None:  # HP_CHANGE
                    val = log.get("value", 0)
                    if val < 0:
                        cur_actions().append(f"     {cname(log['cardId'])} takes {-val} damage!")
                    elif val > 0:
                        cur_actions().append(f"     {cname(log['cardId'])} heals {val} HP!")
                elif t == 9 and cur_actions() is not None:  # CHANGE (knockout -> new active)
                    cur_actions().append(f"     {pflag(p)} sends out {cname(log['cardIdAfter'])}!")
                elif t == 23:  # RESULT
                    res = log.get("result")
                    result_lines.append(f"*** {pflag(res)} WINS! ***" if res in (0, 1) else "*** DRAW ***")

            choice = agent(obs_dict)
            try:
                obs_dict = game.battle_select(choice)
            except IndexError:
                break
            result = obs_dict.get("current", {}).get("result", -1)
            if result != -1:
                for log in obs_dict.get("logs", []):
                    if log.get("type") == 23:
                        res = log.get("result")
                        result_lines.append(f"*** {pflag(res)} WINS! ***" if res in (0, 1) else "*** DRAW ***")
                break
    finally:
        try:
            game.battle_finish()
        except Exception:
            pass

    # Collapse immediately-consecutive blocks with identical real action
    # content (same player, same action lines) into one, keeping the LAST
    # (most final) turn number for the header.
    collapsed: list[dict] = []
    for b in blocks:
        if collapsed and collapsed[-1]["player"] == b["player"]:
            prev_actions, new_actions = collapsed[-1]["actions"], b["actions"]
            if new_actions == prev_actions:
                collapsed[-1]["turn"] = b["turn"]
                continue
            if new_actions[: len(prev_actions)] == prev_actions:
                # Same player's turn continuing with strictly more real
                # actions (a later decision boundary within the same real
                # turn) -- replace with the fuller version, same block.
                collapsed[-1] = b
                continue
        collapsed.append(b)

    for b in collapsed:
        if not b["actions"]:
            continue  # a real TURN_START with no real actions logged under it -- nothing to show
        lines.append("")
        lines.append(f"== Turn {b['turn']} - {pflag(b['player'])} ==")
        lines.extend(b["actions"])
    if result_lines:
        lines.append("")
        lines.extend(result_lines)
    return lines


def render_gif(lines: list[str], out_path: str, cols: int = 62, visible_rows: int = 16,
                font_size: int = 15, ms_per_line: int = 550):
    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", font_size)
        font_dim = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()
        font_dim = font

    char_w = font_size * 0.62
    line_h = int(font_size * 1.55)
    pad = 14
    header_h = 34
    width = int(pad * 2 + cols * char_w)
    height = header_h + pad * 2 + visible_rows * line_h

    bg = (13, 17, 23)
    header_bg = (22, 27, 34)
    fg = (88, 220, 140)
    fg_dim = (110, 120, 135)
    fg_win = (255, 214, 90)
    accent = (240, 246, 252)

    def wrap(line: str) -> list[str]:
        if len(line) <= cols:
            return [line]
        out, cur = [], ""
        for word in line.split(" "):
            if len(cur) + len(word) + 1 > cols:
                out.append(cur)
                cur = word
            else:
                cur = (cur + " " + word).strip()
        if cur:
            out.append(cur)
        return out

    wrapped: list[str] = []
    for ln in lines:
        wrapped.extend(wrap(ln) if ln.strip() else [""])

    frames = []
    total = len(wrapped)
    for i in range(1, total + 1):
        start = max(0, i - visible_rows)
        visible = wrapped[start:i]
        img = Image.new("RGB", (width, height), bg)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, width, header_h], fill=header_bg)
        for k, (cx, cc) in enumerate([(16, (255, 95, 86)), (36, (255, 189, 46)), (56, (39, 201, 63))]):
            d.ellipse([cx, header_h / 2 - 5, cx + 10, header_h / 2 + 5], fill=cc)
        d.text((80, header_h / 2 - font_size / 2 - 1), "pokemon-ai-agent -- real self-play battle log", font=font_dim, fill=(160, 168, 178))
        y = header_h + pad
        for row in visible:
            color = fg
            if row.strip().startswith("=="):
                color = accent
            elif row.strip().startswith(">>"):
                color = (110, 190, 255)
            elif "damage" in row:
                color = (255, 120, 110)
            elif "heals" in row:
                color = (140, 230, 150)
            elif "WINS" in row or "DRAW" in row:
                color = fg_win
            elif not row.strip():
                color = fg_dim
            d.text((pad, y), row, font=font, fill=color)
            y += line_h
        frames.append(img)

    durations = [ms_per_line] * len(frames)
    if frames:
        durations[-1] = 2800  # hold the final (winner) frame longer
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    # This is near-monochrome terminal text on one flat background -- a
    # small, shared, fixed palette compresses dramatically better than
    # PIL's default per-save adaptive quantization while looking identical.
    palette_img = Image.new("P", (1, 1))
    palette_colors = [
        bg, header_bg, fg, fg_dim, fg_win, accent,
        (110, 190, 255), (255, 120, 110), (140, 230, 150),
        (255, 95, 86), (255, 189, 46), (39, 201, 63), (160, 168, 178),
    ]
    flat = []
    for c in palette_colors:
        flat.extend(c)
    flat.extend([0, 0, 0] * (256 - len(palette_colors)))
    palette_img.putpalette(flat)

    quantized = [f.quantize(palette=palette_img, dither=Image.Dither.NONE) for f in frames]
    quantized[0].save(out_path, save_all=True, append_images=quantized[1:],
                       duration=durations, loop=0, optimize=False, disposal=2)
    return out_path, len(frames)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deck", default=os.path.join(REPO_ROOT, "deck.csv"))
    parser.add_argument("--out", default=os.path.join(REPO_ROOT, "docs", "assets", "battle_log.gif"))
    parser.add_argument("--seed-attempts", type=int, default=8,
                         help="real games to try, keeping the most eventful one (most attacks)")
    args = parser.parse_args()

    from cg.api import all_attack, all_card_data

    card_table = {c.cardId: c for c in all_card_data()}
    attack_table = {a.attackId: a for a in all_attack()}
    deck = _load_deck_file(args.deck)

    best_lines, best_score = None, -1
    for attempt in range(args.seed_attempts):
        lines = _play_and_collect_lines(deck, card_table, attack_table)
        score = sum(1 for ln in lines if ln.strip().startswith(">>"))
        print(f"attempt {attempt}: {len(lines)} lines, {score} real attacks")
        if score > best_score:
            best_lines, best_score = lines, score

    print(f"Using the most eventful real game: {best_score} real attacks, {len(best_lines)} lines")
    out_path, n_frames = render_gif(best_lines, args.out)
    print(f"Wrote {n_frames}-frame GIF to {out_path}")


if __name__ == "__main__":
    main()
