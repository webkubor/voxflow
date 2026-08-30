import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import './assets/main.css';

/**
 * naive-ui 按需引入 —— 只注册真正用到的 27 个组件。
 *
 * 原来是 `import naive from 'naive-ui'` + `app.use(naive)`，那是**全量导入**：
 * 整个组件库（80+ 组件）都进 bundle，打出来 1.5 MB，而这个项目一个日期选择器、
 * 一个数据表格、一个日历都没用到。
 *
 * 组件清单是从模板里 grep 出来的（`rg -o "<n-[a-z-]+" src`），不是凭印象列的。
 * 加新组件时记得在这里补一行 —— 忘了的话页面上那个标签会**静默不渲染**，
 * 不报错、只是那块空着，很难查。
 */
import {
  create,
  // 布局
  NLayout, NLayoutHeader, NLayoutContent, NLayoutSider, NGrid, NGridItem, NSpace,
  // 表单
  NForm, NFormItem, NInput, NSelect, NSwitch, NButton, NButtonGroup,
  // 展示
  NAlert, NAvatar, NCard, NEmpty, NList, NListItem, NTag, NText, NThing, NBadge, NSpin, NEllipsis,
  NTabs, NTabPane, NCollapse, NCollapseItem,
  // 浮层
  NModal, NTooltip,
  // provider（useMessage / useDialog 依赖它们）
  NConfigProvider, NMessageProvider, NDialogProvider,
} from 'naive-ui';

const naive = create({
  components: [
    NLayout, NLayoutHeader, NLayoutContent, NLayoutSider, NGrid, NGridItem, NSpace,
    NForm, NFormItem, NInput, NSelect, NSwitch, NButton, NButtonGroup,
    NAlert, NAvatar, NCard, NEmpty, NList, NListItem, NTag, NText, NThing, NBadge, NSpin, NEllipsis,
    NTabs, NTabPane, NCollapse, NCollapseItem,
    NModal, NTooltip,
    NConfigProvider, NMessageProvider, NDialogProvider,
  ],
});

const app = createApp(App);
app.use(naive);
app.use(createPinia());
app.mount('#app');
