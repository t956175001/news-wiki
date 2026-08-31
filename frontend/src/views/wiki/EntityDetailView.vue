<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import dayjs from 'dayjs'
import { getEntity } from '@/api/wiki'
import { ApiError } from '@/api/client'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import PageBack from '@/components/PageBack.vue'
import LinkageGroup from './components/LinkageGroup.vue'
import type { EntityDetail } from '@/types/wiki'

const route = useRoute()

const entity = ref<EntityDetail | null>(null)
const loading = ref(true)
const notFound = ref(false)
const errorMessage = ref('')

async function load() {
  const id = Number(route.params.id)
  loading.value = true
  notFound.value = false
  errorMessage.value = ''
  entity.value = null
  try {
    entity.value = await getEntity(id)
  } catch (e) {
    if (e instanceof ApiError && e.code === 'not_found') {
      notFound.value = true
    } else {
      errorMessage.value = e instanceof Error ? e.message : '加载失败，请稍后重试。'
    }
  } finally {
    loading.value = false
  }
}

watch(() => route.params.id, load, { immediate: true })

function formatDate(value: string | null | undefined) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '—'
}

const confidencePercent = computed(() => Math.round((entity.value?.confidence ?? 0) * 100))
</script>

<template>
  <section class="entity-detail">
    <PageBack fallback="/wiki" label="返回词条库" />

    <div v-if="loading" class="entity-detail__skeleton">
      <a-skeleton
        active
        :title="{ width: '30%' }"
        :paragraph="{ rows: 2, width: ['60%', '40%'] }"
      />
      <a-skeleton active :title="false" :paragraph="{ rows: 5 }" style="margin-top: 40px" />
    </div>

    <div v-else-if="notFound" class="entity-detail__status">
      <p class="entity-detail__status-title">该实体不存在</p>
      <p class="entity-detail__status-desc">它可能已被合并到其他词条，或从未被抽取过。</p>
      <RouterLink to="/wiki" class="entity-detail__back-link">返回词条列表</RouterLink>
    </div>

    <ErrorState v-else-if="errorMessage" :message="errorMessage" @retry="load" />

    <template v-else-if="entity">
      <header class="entity-detail__header">
        <div class="entity-detail__title-row">
          <h1 class="entity-detail__name">{{ entity.name }}</h1>
          <span
            class="entity-detail__type-badge"
            :style="{ '--badge-color': `var(--color-cat-${entity.entity_type})` }"
          >
            {{ entity.entity_type_display }}
          </span>
          <RouterLink
            v-if="entity.linkages.length"
            :to="`/graph?center=e${entity.id}`"
            class="entity-detail__graph-link"
          >
            在图谱中查看 →
          </RouterLink>
        </div>

        <div v-if="entity.aliases.length" class="entity-detail__aliases">
          <a-tag v-for="alias in entity.aliases" :key="alias">{{ alias }}</a-tag>
        </div>

        <p v-if="entity.summary" class="entity-detail__summary">{{ entity.summary }}</p>

        <dl class="entity-detail__stats">
          <div class="entity-detail__stat">
            <dt>置信度</dt>
            <dd>
              <a-progress
                class="entity-detail__confidence-bar"
                :percent="confidencePercent"
                size="small"
                :show-info="false"
                stroke-color="var(--color-accent)"
                trail-color="var(--color-accent-soft)"
              />
              <span class="mono">{{ confidencePercent }}%</span>
            </dd>
          </div>
          <div class="entity-detail__stat">
            <dt>提及次数</dt>
            <dd class="mono">{{ entity.mention_count }}</dd>
          </div>
          <div class="entity-detail__stat">
            <dt>首次出现</dt>
            <dd class="mono">{{ formatDate(entity.first_seen_at) }}</dd>
          </div>
          <div class="entity-detail__stat">
            <dt>最近出现</dt>
            <dd class="mono">{{ formatDate(entity.last_seen_at) }}</dd>
          </div>
        </dl>
      </header>

      <section class="entity-detail__relations">
        <h2 class="entity-detail__relations-title">关系</h2>
        <EmptyState
          v-if="entity.linkages.length === 0"
          title="该实体暂未抽取到关联关系"
          description="换一个实体看看，或等下一次抽取跑完再来。"
        />
        <LinkageGroup v-else :linkages="entity.linkages" />
      </section>
    </template>
  </section>
</template>

<style scoped lang="scss">
.entity-detail {
  max-width: 860px;
  margin: 0 auto;
  padding: var(--space-6) var(--space-5) var(--space-8);
}

.entity-detail__skeleton {
  padding-top: var(--space-4);
}

.entity-detail__status {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-8) var(--space-5);
  text-align: center;
}

.entity-detail__status-title {
  margin: 0;
  font-size: 16px;
  font-family: var(--font-display);
}

.entity-detail__status-desc {
  margin: 0 0 var(--space-2);
  font-size: 13px;
  color: var(--color-text-muted);
}

.entity-detail__back-link {
  display: inline-block;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-pill);
  background: var(--color-accent);
  color: #fff;
  text-decoration: none;
  font-size: 13px;

  &:hover {
    background: var(--color-accent-strong);
  }
}

.entity-detail__header {
  border-bottom: 1px solid var(--color-border);
  padding-bottom: var(--space-5);
  margin-bottom: var(--space-6);
  margin-top: var(--space-3);
}

.entity-detail__graph-link {
  margin-left: auto;
  font-size: 13px;
  color: var(--color-accent-strong);
  text-decoration: none;
  white-space: nowrap;

  &:hover {
    text-decoration: underline;
  }
}

.entity-detail__title-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.entity-detail__name {
  font-size: 32px;
}

.entity-detail__type-badge {
  font-size: 12px;
  font-weight: 600;
  padding: 3px var(--space-3);
  border-radius: var(--radius-pill);
  color: var(--badge-color);
  border: 1px solid var(--badge-color);
  white-space: nowrap;
}

.entity-detail__aliases {
  margin-top: var(--space-3);
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.entity-detail__summary {
  margin: var(--space-4) 0 0;
  font-size: 14.5px;
  line-height: 1.8;
  color: var(--color-text);
  max-width: 68ch;
}

.entity-detail__stats {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-6);
  margin: var(--space-5) 0 0;
}

.entity-detail__stat {
  dt {
    font-size: 11px;
    color: var(--color-text-muted);
    margin-bottom: var(--space-1);
  }

  dd {
    margin: 0;
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: 13px;
  }
}

.entity-detail__confidence-bar {
  width: 72px;
  line-height: 0;
}

.entity-detail__relations-title {
  font-size: 18px;
  margin-bottom: var(--space-4);
}
</style>
