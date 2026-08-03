#!/usr/bin/env python3
"""
Валидатор Universal Assembly Graph (UAG). Используется game-designer при
создании графа и КАЖДЫМ движковым skill (unreal-world-builder,
unity-experience-builder, unigine-simulation-engineer, openusd-architect,
apple-spatial-designer, threejs-web-designer) перед экспортом — не
экспортируй невалидный граф, сначала прогони через этот скрипт.

Проверяет:
1. Обязательные поля / базовую структуру.
2. Что все id в nodes уникальны.
3. Что все ссылки (parent_id, from_node, to_node, target_nodes, target_node)
   указывают на существующие node id.
4. Отсутствие циклов в иерархии parent_child.
5. (warning, не ошибка) типы узлов/триггеры, для которых нет известного
   движкового маппинга — печатается как предупреждение, не блокирует.
"""

import argparse
import json
import sys

KNOWN_NODE_TYPES = {
    "mesh", "light", "camera", "trigger_volume",
    "ui_panel", "particle_emitter", "audio_source", "group", "custom",
}
KNOWN_CONNECTION_TYPES = {
    "parent_child", "joint_fixed", "joint_hinge", "joint_slider", "data_link",
}
KNOWN_CONSTRAINT_TYPES = {
    "physics_collision", "interaction_grabbable", "animation_trigger", "logic_rule",
}
KNOWN_TRIGGERS = {"on_grab", "on_proximity", "on_gaze", "on_click", "on_timer"}


def validate(uag: dict) -> dict:
    errors = []
    warnings = []

    if "nodes" not in uag or not isinstance(uag["nodes"], list):
        errors.append("Отсутствует или некорректно поле 'nodes' (должен быть список).")
        return {"valid": False, "errors": errors, "warnings": warnings}

    node_ids = set()
    for i, node in enumerate(uag["nodes"]):
        nid = node.get("id")
        if not nid:
            errors.append(f"nodes[{i}]: отсутствует 'id'.")
            continue
        if nid in node_ids:
            errors.append(f"nodes[{i}]: дублирующийся id '{nid}'.")
        node_ids.add(nid)
        if node.get("type") not in KNOWN_NODE_TYPES:
            warnings.append(
                f"node '{nid}': тип '{node.get('type')}' не входит в известный список "
                f"({sorted(KNOWN_NODE_TYPES)}) — движковый skill должен явно сообщить "
                f"пользователю, что маппинг для этого типа не определён, а не пропустить молча."
            )

    # Проверка parent_id + сбор рёбер иерархии для поиска циклов
    parent_of = {}
    for node in uag["nodes"]:
        nid = node.get("id")
        pid = node.get("parent_id")
        if pid is not None:
            if pid not in node_ids:
                errors.append(f"node '{nid}': parent_id '{pid}' не существует среди nodes.")
            else:
                parent_of[nid] = pid

    # Поиск циклов в parent_child
    for start in list(parent_of.keys()):
        seen = set()
        cur = start
        while cur in parent_of:
            if cur in seen:
                errors.append(f"Обнаружен цикл в иерархии parent_child, включающий узел '{start}'.")
                break
            seen.add(cur)
            cur = parent_of[cur]

    # connections
    for i, conn in enumerate(uag.get("connections", [])):
        ctype = conn.get("type")
        if ctype not in KNOWN_CONNECTION_TYPES:
            warnings.append(f"connections[{i}]: неизвестный тип '{ctype}'.")
        for field in ("from_node", "to_node"):
            ref = conn.get(field)
            if ref is not None and ref not in node_ids:
                errors.append(f"connections[{i}]: {field} '{ref}' не существует среди nodes.")

    # constraints
    for i, constr in enumerate(uag.get("constraints", [])):
        ctype = constr.get("type")
        if ctype not in KNOWN_CONSTRAINT_TYPES:
            warnings.append(f"constraints[{i}]: неизвестный тип '{ctype}'.")
        for ref in constr.get("target_nodes", []):
            if ref not in node_ids:
                errors.append(f"constraints[{i}]: target_nodes содержит несуществующий id '{ref}'.")

    # interactions
    for i, inter in enumerate(uag.get("interactions", [])):
        trig = inter.get("trigger")
        if trig not in KNOWN_TRIGGERS:
            warnings.append(f"interactions[{i}]: неизвестный триггер '{trig}'.")
        ref = inter.get("target_node")
        if ref is not None and ref not in node_ids:
            errors.append(f"interactions[{i}]: target_node '{ref}' не существует среди nodes.")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings, "node_count": len(node_ids)}


def main():
    parser = argparse.ArgumentParser(description="Валидация Universal Assembly Graph (UAG)")
    parser.add_argument("uag_file", help="Путь к JSON-файлу с UAG")
    args = parser.parse_args()

    with open(args.uag_file, "r", encoding="utf-8") as f:
        uag = json.load(f)

    result = validate(uag)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
