<script setup lang="ts">
import { ElContainer, ElMenu, ElMenuItem } from 'element-plus'
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <ElContainer class="flex-col">
    <!-- 全局导航栏 -->
    <div class="sticky top-0 z-20 border-b border-gray-200 bg-white">
      <ElMenu mode="horizontal" :default-active="route.path" router :ellipsis="false" class="px-2">
        <div class="mr-6 flex items-center">
          <span class="text-base font-bold text-gray-800">量化工作台</span>
        </div>
        <ElMenuItem index="/">行情监控</ElMenuItem>
        <ElMenuItem index="/strategies">策略中心</ElMenuItem>
      </ElMenu>
    </div>
    <RouterView />
  </ElContainer>
</template>
