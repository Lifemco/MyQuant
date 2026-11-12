<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { DataAnalysis, TrendCharts, SetUp, Fold, Expand } from '@element-plus/icons-vue'
const route = useRoute()
const collapsed = ref(false)
const entries = [
  { path: '/market', title: '市场总览', short: '总览', icon: DataAnalysis },
  { path: '/', title: '行情监控', short: '行情', icon: TrendCharts },
  { path: '/strategies', title: '策略中心', short: '策略', icon: SetUp },
]
</script>
<template>
  <div class="app-layout" :class="{ 'nav-collapsed': collapsed }">
    <aside class="app-sidebar" aria-label="工作台侧栏">
      <RouterLink to="/market" class="brand" aria-label="MyQuant 市场总览"
        ><span class="brand-symbol">Q</span
        ><span class="brand-text">MyQuant<small>个人量化工作台</small></span></RouterLink
      >
      <nav aria-label="主导航">
        <div role="menu" aria-orientation="vertical" class="nav-links">
          <RouterLink
            v-for="item in entries"
            :key="item.path"
            :to="item.path"
            role="menuitem"
            :aria-label="item.title"
            :aria-current="route.path === item.path ? 'page' : undefined"
            :title="item.title"
            class="nav-link"
            :class="{ active: route.path === item.path }"
            ><component :is="item.icon" class="nav-icon" aria-hidden="true" /><span
              class="nav-title"
              >{{ item.title }}</span
            ><span class="nav-short">{{ item.short }}</span></RouterLink
          >
        </div>
      </nav>
      <div class="sidebar-bottom">
        <p class="sidebar-caption">研究 · 验证 · 决策</p>
        <button
          class="collapse-nav"
          :aria-label="collapsed ? '展开导航' : '收起导航'"
          :aria-expanded="!collapsed"
          @click="collapsed = !collapsed"
        >
          <component :is="collapsed ? Expand : Fold" class="nav-icon" /><span>收起导航</span>
        </button>
      </div>
    </aside>
    <div class="app-content"><RouterView /></div>
  </div>
</template>
<style scoped>
.app-layout {
  --nav-width: 188px;
  display: grid;
  grid-template-columns: var(--nav-width) minmax(0, 1fr);
  min-height: 100dvh;
  background: #f5f7fa;
}
.app-layout.nav-collapsed {
  --nav-width: 68px;
}
.app-sidebar {
  position: sticky;
  top: 0;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #e7eaf0;
  background: #fff;
  padding: 26px 12px 16px;
  box-sizing: border-box;
}
.brand {
  display: flex;
  align-items: center;
  gap: 9px;
  color: #182337;
  text-decoration: none;
  margin: 0 4px 34px;
}
.brand-symbol {
  display: grid;
  place-items: center;
  background: #d63642;
  color: white;
  border-radius: 10px;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  font:
    bold 24px Georgia,
    serif;
}
.brand-text {
  font-size: 19px;
  font-weight: 700;
  letter-spacing: -0.04em;
}
.brand-text small {
  display: block;
  font-size: 10px;
  color: #8a94a6;
  font-weight: 400;
  letter-spacing: 0.04em;
  margin-top: 3px;
}
.nav-links {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.nav-link {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 13px 12px;
  border-radius: 8px;
  color: #667085;
  text-decoration: none;
  font-size: 14px;
}
.nav-link:hover {
  background: #f8fafc;
}
.nav-link.active {
  color: #d33643;
  background: #fff1f2;
  font-weight: 600;
}
.nav-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}
.nav-short {
  display: none;
}
.sidebar-bottom {
  margin-top: auto;
}
.sidebar-caption {
  color: #9ba3b1;
  font-size: 10px;
  text-align: center;
}
.collapse-nav {
  display: flex;
  gap: 10px;
  align-items: center;
  width: 100%;
  padding: 12px;
  color: #8590a1;
  font-size: 12px;
  border: 0;
  background: none;
  cursor: pointer;
}
.app-content {
  min-width: 0;
}
.nav-collapsed .brand-text,
.nav-collapsed .nav-title,
.nav-collapsed .sidebar-caption,
.nav-collapsed .collapse-nav span {
  display: none;
}
.nav-collapsed .nav-link {
  justify-content: center;
  padding: 13px 0;
}
@media (max-width: 760px) {
  .app-layout,
  .app-layout.nav-collapsed {
    --nav-width: 60px;
  }
  .app-sidebar {
    padding: 18px 5px;
  }
  .brand {
    margin: 0 auto 26px;
  }
  .brand-symbol {
    width: 32px;
    height: 32px;
  }
  .brand-text,
  .nav-title,
  .sidebar-bottom {
    display: none !important;
  }
  .nav-link {
    flex-direction: column;
    gap: 5px;
    padding: 11px 0 !important;
    font-size: 10px;
  }
  .nav-short {
    display: inline;
  }
  .nav-icon {
    width: 19px;
    height: 19px;
  }
}
</style>
