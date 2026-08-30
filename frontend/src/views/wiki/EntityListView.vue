<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { listEntities } from '@/api/wiki'
import LoadingPanel from '@/components/LoadingPanel.vue'
import ErrorState from '@/components/ErrorState.vue'
import EmptyState from '@/components/EmptyState.vue'
import { ENTITY_TYPE_OPTIONS } from '@/constants/entityTypes'
import type { EntitySummary, EntityType } from '@/types/wiki'

const SORT_OPTIONS = [
  { value: '-mention_count', label: '提及次数 · 高到低' },
  { value: '-confidence', label: '置信度 · 高到低' },
  { value: '-last_seen_at', label: '最近出现 · 新到旧' },
  { value: 'name', label: '名称 · A → Z' },
]

const PAGE_SIZE = 20

const router = useRouter()

const search = ref('')
const entityType = ref<EntityType | undefined>(undefined)
const ordering = ref('-mention_count')
const page = ref(1)

const loading = ref(true)
const errorMessage = ref('')
const entities = ref<EntitySummary[]>([])
const total = ref(0)

let searchDebounce: ReturnType<typeof setTimeout> | null = null

async function fetchEntities() {
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await listEntities({
      search: search.value || undefined,
      entity_type: entityType.value,
      ordering: ordering.value,
      page: page.value,
      page_size: PAGE_SIZE,
    })
    entities.value = data.results
    total.value = data.count
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : '加载失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

// Search gets a debounce of its own; filter/sort changes are already discrete
// clicks and should refetch immediately.
watch(search, () => {
  if (searchDebounce) clearTimeout(searchDebounce)
  searchDebounce = setTimeout(() => {
    page.value = 1
    fetchEntities()
  }, 300)
})

watch([entityType, ordering], () => {
  page.value = 1
  fetchEntities()
})

watch(page, fetchEntities)

onMounted(fetchEntities)

function goToDetail(id: number) {
  router.push(`/wiki/${id}`)
}

function truncate(text: string, max = 88) {
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max)}…` : text
}
</script>

<template>
  <section class="entity-list">
    <header class="entity-list__toolbar">
      <a-input-search
        v-model:value="search"
        placeholder="搜索实体名称或别名…"
        allow-clear
        class="entity-list__search"
      />
      <a-select
        v-model:value="entityType"
        :options="ENTITY_TYPE_OPTIONS"
        allow-clear
        placeholder="全部类型"
        class="entity-list__filter"
      />
      <a-select v-model:value="ordering" :options="SORT_OPTIONS" class="entity-list__sort" />
    </header>

    <LoadingPanel v-if="loading" tip="加载词条中…" />
    <ErrorState v-else-if="errorMessage" :message="errorMessage" @retry="fetchEntities" />
    <EmptyState
      v-else-if="entities.length === 0"
      title="没有匹配的实体"
      description="换个关键词或筛选条件试试。"
    />

    <template v-else>
      <div class="entity-list__grid">
        <button
          v-for="entity in entities"
          :key="entity.id"
          type="button"
          class="entity-card"
          @click="goToDetail(entity.id)"
        >
          <div class="entity-card__top">
            <h3 class="entity-card__name">{{ entity.name }}</h3>
            <span
              class="entity-card__badge"
              :style="{ '--badge-color': `var(--color-cat-${entity.entity_type})` }"
            >
              {{ entity.entity_type_display }}
            </span>
          </div>
          <p class="entity-card__summary">{{ truncate(entity.summary) || '暂无摘要。' }}</p>
          <div class="entity-card__meta mono">提及 {{ entity.mention_count }} 次</div>
        </button>
      </div>

      <a-pagination
        v-model:current="page"
        :total="total"
        :page-size="PAGE_SIZE"
        show-less-items
        class="entity-list__pagination"
      />
    </template>
  </section>
</template>

<style scoped lang="scss">
.entity-list {
  padding: var(--space-6) var(--space-5) var(--space-8);
}

.entity-list__toolbar {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
  flex-wrap: wrap;
}

.entity-list__search {
  flex: 1 1 280px;
  max-width: 400px;
}

.entity-list__filter,
.entity-list__sort {
  width: 180px;
}

.entity-list__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: var(--space-4);
}

.entity-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  text-align: left;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  cursor: pointer;
  font: inherit;
  color: inherit;
  transition:
    border-color var(--duration-fast) var(--ease-standard),
    box-shadow var(--duration-fast) var(--ease-standard),
    transform var(--duration-fast) var(--ease-standard);

  &:hover {
    border-color: var(--color-accent);
    box-shadow: var(--shadow-md);
    transform: translateY(-1px);
  }
}

.entity-card__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
}

.entity-card__name {
  font-size: 17px;
  line-height: 1.3;
}

.entity-card__badge {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  padding: 2px var(--space-2);
  border-radius: var(--radius-pill);
  color: var(--badge-color);
  border: 1px solid var(--badge-color);
  white-space: nowrap;
}

.entity-card__summary {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-muted);
  flex: 1;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.entity-card__meta {
  font-size: 11px;
  color: var(--color-text-muted);
}

.entity-list__pagination {
  margin-top: var(--space-6);
  display: flex;
  justify-content: center;
}
</style>
