# Store 划分

## 为什么从 provide/inject 换成 Pinia

原来 `MainLayout.vue` 一个组件里装了 **21 个 ref/reactive**，然后整包
`provide('state', {...})` / `provide('actions', {...})` 丢给 5 个子组件，
子组件靠 `inject('state')` 解构自己要的那几个。

三个实际代价：

1. **依赖看不见**。`inject('state')` 拿到的是什么、少了会怎样，全靠约定 ——
   打错一个字段名不报错，只是那个值永远 `undefined`。
2. **状态改在哪查不出来**。所有 action 都挂在同一个 `actions` 对象上，
   要查「谁改了 selectedPersona」得全局搜字符串。
3. **MainLayout 变成杂物间**。它本该只管布局，现在同时管音色、任务、播放器、
   Suno、LLM、流水线 —— 800 多行，改任何一块都要在里面找位置。

Pinia 的好处不是「更现代」，是**边界**：每个 store 只管一个域，
`useXxxStore()` 一眼看出这个组件依赖什么。

## 按域拆，不按组件拆

划分依据是「这些状态会一起变吗」，不是「哪个组件用它」：

| Store | 管什么 | 原来在 MainLayout 的 |
|---|---|---|
| `voices` | 音色库、当前选中音色、预览播放 | `personas` `selectedPersona` `previewKey` `previewProgress` `previewPlayer` |
| `synth` | 克隆合成 + 音色设计的表单与提交 | `cloneForm` `designForm` `designPresets` `savedScripts` |
| `tasks` | 任务队列、进度轮询 | `tasks` `taskPanelCollapsed` `globalLoading` `globalLoadingText` |
| `library` | 音频库、全局播放器 | `audioFiles` `player` |
| `suno` | Suno 登录态、出歌表单 | `suno` `sunoForm` |
| `capabilities` | 四项能力状态（模型/Suno/中台/LLM） | `caps` `modelStatus` `llm` |
| `pipeline` | 作品流水线状态（草稿→出歌→选定→发版→上架） | 新增，见 `core/pipeline.py` |

`currentTab` 留在 MainLayout —— 那是纯 UI 状态，不跨组件共享。

## 约定

- **一个 store 一个文件**，用 setup 语法（`defineStore('x', () => {...})`），
  跟组件写法一致，不用记 options 那套 state/getters/actions 分区。
- **action 里做请求，组件里不写 fetch**。组件只调 `store.loadXxx()`，
  这样「哪个接口被谁调」在 store 里一目了然。
- **失败不要静默**。catch 里至少要设一个 error 字段或抛出来 ——
  今天已经踩过好几次「不报错只是没生效」的坑。
