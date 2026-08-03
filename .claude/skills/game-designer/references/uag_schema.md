# Universal Assembly Graph (UAG) — схема v0.1

UAG — это engine-neutral JSON-описание сцены/взаимодействия, которое `game-designer` производит один раз, а каждый движковый skill (`unreal-world-builder`, `unity-experience-builder`, `unigine-simulation-engineer`, `openusd-architect`, `apple-spatial-designer`, `threejs-web-designer`) переводит в родные примитивы своего движка. Это не стандарт индустрии — это внутренний формат qFoldIT, спроектированный, чтобы избежать переписывания логики сцены 6 раз под 6 движков.

## Структура

```json
{
  "uag_version": "0.1",
  "metadata": {
    "name": "МАС Снежинка — оранжерея",
    "description": "string, человеко-читаемое описание сцены",
    "source_context": "например: 'plant-growth скилл, результат для NPK-дефицита K'"
  },
  "nodes": [
    {
      "id": "greenhouse_plant_01",
      "type": "mesh | light | camera | trigger_volume | ui_panel | particle_emitter | audio_source | group | custom",
      "transform": {
        "position": [0.0, 0.0, 0.0],
        "rotation_euler_deg": [0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0]
      },
      "properties": {
        "mesh_ref": "опционально: путь/имя ассета, если type=mesh",
        "color": "опционально, hex или engine-agnostic имя",
        "intensity": "опционально, для light"
      },
      "parent_id": "id родителя или null"
    }
  ],
  "connections": [
    {
      "id": "string",
      "type": "parent_child | joint_fixed | joint_hinge | joint_slider | data_link",
      "from_node": "id",
      "to_node": "id",
      "properties": {}
    }
  ],
  "constraints": [
    {
      "id": "string",
      "type": "physics_collision | interaction_grabbable | animation_trigger | logic_rule",
      "target_nodes": ["id", "..."],
      "properties": {}
    }
  ],
  "interactions": [
    {
      "id": "string",
      "trigger": "on_grab | on_proximity | on_gaze | on_click | on_timer",
      "target_node": "id",
      "action": "engine-agnostic текстовое описание того, что должно произойти"
    }
  ]
}
```

## Принцип: UAG не знает про движки

Ни одно поле UAG не должно содержать имя класса конкретного движка (`UStaticMeshComponent`, `GameObject`, `Entity`, `<mesh>` и т.д.) — это обязанность движкового skill'а при экспорте. Если в UAG проникает движко-специфичная деталь, это сигнал, что она должна была быть в `properties` конкретного узла в engine-agnostic форме, а маппинг — на стороне адаптера.

## Таблица маппинга (для авторов движковых skills)

| UAG-концепция | Unreal | Unity | Unigine | OpenUSD | RealityKit | Three.js/R3F |
|---|---|---|---|---|---|---|
| `node type=mesh` | StaticMeshActor | GameObject + MeshRenderer | ObjectMeshStatic | Xform + Mesh prim | Entity + ModelComponent | `<mesh>` |
| `node type=light` | PointLight/DirectionalLight актор | GameObject + Light | LightWorld/LightPoint | Xform + UsdLuxLight | Entity + PointLight/DirectionalLight | `<pointLight>`/`<directionalLight>` |
| `connection type=parent_child` | Attach to component | Transform.SetParent | Node.setParent | Prim hierarchy (SdfPath) | Entity.addChild | React children |
| `constraint type=physics_collision` | Collision component/preset | Collider + Rigidbody | BodyRigid | UsdPhysics schema | CollisionComponent | Rapier/cannon-es rigidbody |
| `interaction trigger=on_grab` | Enhanced Input + Interaction Component | XR Interaction Toolkit Grabbable | Unigine Input + custom logic | (не входит в USD напрямую, нужен runtime-слой) | Gesture recognizer / ARKit hand tracking | `@react-three/xr` interaction |

Это ориентировочная таблица, не исчерпывающая — каждый движковый skill должен уточнять маппинг для реально встретившихся типов узлов, а не ограничиваться этой таблицей.

## Валидация перед экспортом

Любой движковый skill, ПЕРЕД тем как звать MCP-инструменты конкретного движка, обязан:
1. Проверить, что все `parent_id`/`from_node`/`to_node`/`target_node(s)` ссылаются на существующие `id` в `nodes`.
2. Проверить на циклы в иерархии `parent_child`.
3. Явно сообщить пользователю о любых `type`/`trigger`, для которых у этого конкретного движка ещё нет реализованного маппинга (см. таблицу выше) — не пропускать узел молча.
