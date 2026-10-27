| Category | Capability | Status | Evidence | Note |
| --- | --- | --- | --- | --- |
| Action framework | Action lifecycle | supported | `tests/test_backend.py::test_sync_scenario_completes_and_emits_event` | py_trees SUCCESS/RUNNING/FAILURE is mapped to scenario state |
| Action framework | Actor binding | supported | `tests/test_backend.py::test_keep_constraints_bind_actor_attributes` | keep(it.name == ...) and role_name binding |
| Action framework | Composition | supported | `tests/test_backend.py::test_serial_parallel_and_one_of_mapping` | serial / parallel / one_of |
| Action framework | Duration handling | partial | `scenarios/dev/stage3_parallel.osc`<br>`tests/test_backend.py::test_parallel_waits_for_slowest_branch` | wait elapsed() is supported; no automatic parallel timeout wrapper |
| Movement | Drive | supported | `scenarios/dev/stage3_sync.osc`<br>`tests/test_carla.py::test_adapter_spawns_and_moves` | durative target-speed behaviour on both adapters |
| Movement | Walk | partial | `tests/test_backend.py::test_pedestrian_walk_moves_actor` | pedestrian walk works on the mock adapter; CarlaAdapter spawns vehicles and environment only |
| Movement | Speed control | partial | `src/osc2c/backend/method_registry.py`<br>`src/osc2c/adapters/carla.py` | instant setpoint on mock; proportional throttle/brake on CARLA, no integral term |
| Movement | Acceleration control | unsupported | — | no acceleration behaviour or acceleration modifier is mapped |
| Movement | Stationary | supported | `scenarios/carla/cut_in.osc` | target speed 0 plus brake at initialisation |
| Position & path | Assign position (absolute) | supported | `scenarios/dev/placement_modes.osc`<br>`tests/test_carla.py::test_cut_in_scenario_runs_on_carla` | x/y/z or OpenDRIVE lane placement |
| Position & path | Assign orientation | partial | `src/osc2c/adapters/carla.py` | heading/yaw is supported; pitch and roll are not exposed |
| Position & path | Follow path | unsupported | — | no spline/path routing; vehicles follow the current lane |
| Position & path | Follow trajectory | unsupported | — | no time-parameterised trajectory tracking |
| Position & path | Time gap | unsupported | — | no time-gap or TTC query; only spatial queries exist |
| Position & path | Space gap | supported | `tests/test_backend.py::test_sync_scenario_completes_and_emits_event` | position.ahead_of() and position.euclidean() |
| Position & path | Headway | partial | `scenarios/carla/cut_in.osc` | relative spatial headway via vector projection; no time headway |
| Environment | Weather control | unsupported | — | adapter saves/restores weather but no OSC behaviour changes it |
| Environment | Traffic signals | unsupported | — | traffic lights are not read or controlled |
| Environment | Road conditions | unsupported | — | no surface/friction changes |
| Environment | Celestial position | supported | `scenarios/dev/environment_lights.osc` | azimuth/elevation are applied to the adapter environment state |
| Modifiers | Speed modifier | supported | `scenarios/dev/lane_change_speed.osc` | speed(speed:, at:) |
| Modifiers | Acceleration modifier | unsupported | — | not declared in the fallback standard library |
| Modifiers | Position modifier | supported | `scenarios/dev/placement_modes.osc` | distance + ahead_of/behind and absolute x/y/z |
| Modifiers | Lateral modifier | supported | `scenarios/carla/cut_in.osc` | lane(side:, side_of:) maps to OpenDRIVE lane offsets |
| Modifiers | Physical movement | partial | `src/osc2c/adapters/carla.py` | engine physics while driving; teleport for placement; no physics toggle |
| Modifiers | Temporal modifiers | supported | `tests/test_backend.py::test_elapsed_accepts_milliseconds` | elapsed() with SI time values |
| Modifiers | Relative modifiers | supported | `scenarios/dev/placement_modes.osc` | ahead_of / behind / side_of |
| Modifiers | Orientation modifiers | partial | `src/osc2c/backend/method_registry.py` | h (yaw) is accepted; no pitch/roll modifiers |
| Coordinate systems | Global frame (x-y-z) | supported | `scenarios/dev/placement_modes.osc` | absolute Cartesian placement |
| Coordinate systems | Relative coordinates | supported | `scenarios/dev/placement_modes.osc` | actor-relative distance and lane offset |
| Coordinate systems | Road frame (s-t) | partial | `src/osc2c/adapters/mock.py` | mock exposes s/lane; CARLA keeps waypoint s internally but does not expose t |
| Coordinate systems | Route-based (s-t) | unsupported | — | no route construction or route-relative queries |
| Scenario composition | Serial execution | supported | `tests/test_backend.py::test_serial_parallel_and_one_of_mapping` | Sequence(memory=True) |
| Scenario composition | Parallel execution | supported | `tests/test_backend.py::test_parallel_waits_for_slowest_branch` | Parallel(SuccessOnAll) |
| Scenario composition | Event-driven execution | supported | `scenarios/dev/event_handshake.osc`<br>`tests/test_backend.py::test_latched_event_satisfies_later_wait` | latched blackboard events |
| Scenario composition | Conditional triggers | supported | `scenarios/dev/stage3_fall.osc` | elapsed, rise, fall and @event |
| Scenario composition | Custom behaviour | partial | `tests/test_backend.py::test_user_defined_actor_method_is_evaluated` | user expression methods and action bodies; no action inheritance merging |
| Scenario composition | Custom actions | supported | `scenarios/dev/action_calls.osc`<br>`tests/test_backend.py::test_action_call_accepts_actor_parameter_and_defaults` | action bodies compile to scoped subtrees with positional/named arguments and defaults |
| Scenario composition | Conflict resolution | partial | `tests/test_backend.py::test_serial_parallel_and_one_of_mapping` | one_of first-success arbitration; no priority or conflict policies |
| Scenario composition | Semantic validation | supported | `tests/test_semantics.py` | scopes, types, units and stable diagnostic codes |
| Scenario composition | one_of | supported | `tests/test_backend.py::test_serial_parallel_and_one_of_mapping` | Parallel(SuccessOnOne) |
| Scenario composition | rise | supported | `tests/test_backend.py::test_rise_does_not_fire_on_an_already_true_condition` | edge detection |
| Scenario composition | fall | supported | `tests/test_backend.py::test_fall_edge_fires_after_speed_drops` | edge detection |

Total 43: 24 supported, 10 partial, 9 unsupported (strict 56%, weighted 67%).
