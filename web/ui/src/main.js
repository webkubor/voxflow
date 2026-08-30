import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import { router } from './router';
import './assets/main.css';

/**
 * naive-ui 的组件**不在这里注册** —— 交给 unplugin-vue-components 的
 * NaiveUiResolver 按模板自动解析（见 vite.config.js）。
 *
 * 这里以前是一份手工维护的 27 个组件清单。问题是加了新组件忘了补的话，
 * 那个标签会**静默不渲染**：不报错、不警告，页面上那块就是空的。
 * 今天栽了两次 —— 平台切换器和已上架表格都这么凭空消失过一次。
 *
 * 自动解析之后这类错误从根上不存在，而且 tree-shaking 只打包真正用到的。
 */
const app = createApp(App);
app.use(createPinia());
app.use(router);
app.mount('#app');
