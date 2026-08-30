<script setup lang="ts">
import type { TableColumnsType } from 'ant-design-vue'
import LoadingPanel from './LoadingPanel.vue'
import ErrorState from './ErrorState.vue'
import EmptyState from './EmptyState.vue'

withDefaults(
  defineProps<{
    columns: TableColumnsType
    dataSource: Record<string, unknown>[]
    rowKey: string
    loading?: boolean
    errorMessage?: string
    emptyText?: string
  }>(),
  {
    loading: false,
    errorMessage: '',
    emptyText: '暂无数据',
  },
)

const emit = defineEmits<{ retry: [] }>()
</script>

<template>
  <LoadingPanel v-if="loading" />
  <ErrorState v-else-if="errorMessage" :message="errorMessage" @retry="emit('retry')" />
  <EmptyState v-else-if="dataSource.length === 0" :title="emptyText" />
  <a-table v-else :columns="columns" :data-source="dataSource" :row-key="rowKey">
    <template v-for="(_, slotName) in $slots" #[slotName]="slotProps" :key="slotName">
      <slot :name="slotName" v-bind="slotProps" />
    </template>
  </a-table>
</template>
