# 旅行时间规划数据规范 (Data Schema)

本文档描述了旅行时间规划可视化组件所需的 JSON 数据结构。

## 根对象 (Root Object)

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `code` | Integer | 状态码 (例如 200)。可选，为了保持 API 兼容性建议包含。 |
| `message` | String | 状态消息。可选。 |
| `data` | Object | **必需**。用于存放方案数据。 |
| `data.plans` | Array | **必需**。旅行方案对象的列表。 |

## 方案对象 (Plan Object)

`data.plans` 中的每一项都代表一个可选的出行方案。

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `plan_id` | String | 方案的唯一标识。 |
| `title` | String | 展示标题，例如 "方案一：高铁出行"。 |
| `tags` | Array<String> | 标签列表，用于直观展示，例如 ["最快", "舒适"]。 |
| `summary` | Object | 摘要指标。 |
| `summary.total_duration_minutes` | Number | 总时长（分钟）。 |
| `summary.total_cost` | Number | 总费用（数值）。 |
| `summary.departure_time` | String (ISO 8601) | 例如 "2023-10-27T07:00:00"。 |
| `summary.arrival_time` | String (ISO 8601) | 例如 "2023-10-27T09:45:00"。 |
| `segments` | Array | 方案的时间轴段落列表。 |

## 路线段对象 (Segment Object)

每个段落代表一段行程或是一段等待时间。

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `segment_id` | String | 唯一标识。 |
| `type` | String | "transit"（行程） 或 "wait"（等待）。 |
| `description` | String | 文本描述，例如 "北京西 - 保定东"。 |
| `start_time` | String (ISO 8601) | 段落开始时间。 |
| `end_time` | String (ISO 8601) | 段落结束时间。 |
| `duration_minutes` | Number | 持续分钟数。 |
| `location` | Object | `{ "start": "出发地", "end": "目的地" }`。 |
| `transport_detail` | Object | 对于 "wait" 类型可选。 |
| `transport_detail.mode` | String | "train" (火车), "subway" (地铁), "bus" (公交), "taxi" (打车), "walk" (步行), "plane" (飞机), "wait" (等待)。 |
| `transport_detail.identifier` | String | 可选。车次或航班号 (例如 "G601")。 |

## 数据注入与使用
要使用此数据，可将根对象传递给：
```javascript
window.renderSchedule(jsonData);
```
或者通过 window message 发送：
```javascript
iframe.contentWindow.postMessage({
    type: 'UPDATE_SCHEDULE',
    payload: jsonData
}, '*');
```
