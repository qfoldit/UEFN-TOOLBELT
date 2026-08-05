# Universal Assembly Graph (UAG) — schema v0.1

UAG is an engine-neutral JSON description of a scene/interaction, produced once by `game-designer`, which each engine-specific skill (`unreal-world-builder`, `unity-experience-builder`, `unigine-simulation-engineer`, `openusd-architect`, `apple-spatial-designer`, `threejs-web-designer`) translates into its own engine's native primitives. This is not an industry standard — it's qFoldIT's own internal format, designed to avoid rewriting the same scene logic six times for six different engines.

## Structure

```json
{
  "uag_version": "0.1",
  "metadata": {
    "name": "MAS Snowflake — greenhouse",
    "description": "string, human-readable description of the scene",
    "source_context": "e.g.: 'plant-growth skill, result for NPK potassium deficiency'"
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
        "mesh_ref": "optional: asset path/name, if type=mesh",
        "color": "optional, hex or engine-agnostic name",
        "intensity": "optional, for light"
      },
      "parent_id": "parent's id or null"
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
      "action": "engine-agnostic text description of what should happen"
    }
  ]
}
```

## Principle: UAG doesn't know about engines

No UAG field should contain a concrete engine's class name (`UStaticMeshComponent`, `GameObject`, `Entity`, `<mesh>`, etc.) — that's the engine-specific skill's job at export time. If an engine-specific detail leaks into UAG, that's a signal it should have been in that node's `properties` in engine-agnostic form instead, with the mapping handled on the adapter's side.

## Mapping table (for authors of engine-specific skills)

| UAG concept | Unreal | Unity | Unigine | OpenUSD | RealityKit | Three.js/R3F |
|---|---|---|---|---|---|---|
| `node type=mesh` | StaticMeshActor | GameObject + MeshRenderer | ObjectMeshStatic | Xform + Mesh prim | Entity + ModelComponent | `<mesh>` |
| `node type=light` | PointLight/DirectionalLight actor | GameObject + Light | LightWorld/LightPoint | Xform + UsdLuxLight | Entity + PointLight/DirectionalLight | `<pointLight>`/`<directionalLight>` |
| `connection type=parent_child` | Attach to component | Transform.SetParent | Node.setParent | Prim hierarchy (SdfPath) | Entity.addChild | React children |
| `constraint type=physics_collision` | Collision component/preset | Collider + Rigidbody | BodyRigid | UsdPhysics schema | CollisionComponent | Rapier/cannon-es rigidbody |
| `interaction trigger=on_grab` | Enhanced Input + Interaction Component | XR Interaction Toolkit Grabbable | Unigine Input + custom logic | (not directly part of USD, needs a runtime layer) | Gesture recognizer / ARKit hand tracking | `@react-three/xr` interaction |

This is an indicative table, not an exhaustive one — each engine-specific skill should refine the mapping for node types it actually encounters, rather than limiting itself to this table.

## Validation before export

Any engine-specific skill, BEFORE calling that engine's own MCP tools, must:
1. Verify that every `parent_id`/`from_node`/`to_node`/`target_node(s)` references an existing `id` in `nodes`.
2. Check for cycles in the `parent_child` hierarchy.
3. Explicitly tell the user about any `type`/`trigger` for which that specific engine doesn't yet have an implemented mapping (see the table above) — never skip a node silently.
