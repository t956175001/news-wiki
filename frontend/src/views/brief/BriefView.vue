<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import dayjs from 'dayjs'
import { getBriefByDate, getLatestBrief, listBriefs } from '@/api/brief'
import { ApiError } from '@/api/client'
import { renderBriefContent } from './renderBrief'
import LoadingPanel from '@/components/LoadingPanel.vue'
import ErrorState from '@/components/ErrorState.vue'
import EmptyState from '@/components/EmptyState.vue'
import type { DailyBriefDetail } from '@/types/brief'

const brief = ref<DailyBriefDetail | null>(null)
// Newest-first, mirrors DailyBrief.Meta.ordering — powers the prev/next
// buttons and the date dropdown without a second sort on the frontend.
const availableDates = ref<string[]>([])
const loading = ref(true)
const noBrief = ref(false)
const errorMessage = ref('')

const renderedContent = computed(() =>
  brief.value ? renderBriefContent(brief.value.content_md) : '',
)

const currentIndex = computed(() =>
  brief.value ? availableDates.value.indexOf(brief.value.date) : -1,
)
const hasNewer = computed(() => currentIndex.value > 0)
const hasOlder = computed(
  () => currentIndex.value !== -1 && currentIndex.value < availableDates.value.length - 1,
)

async function loadDateList() {
  try {
    const data = await listBriefs({ page_size: 100 })
    availableDates.value = data.results.map((item) => item.date)
  } catch {
    // The date switcher is a convenience; the main content load below still
    // runs and surfaces its own error if the API is actually down.
  }
}

async function loadLatest() {
  loading.value = true
  errorMessage.value = ''
  noBrief.value = false
  try {
    brief.value = await getLatestBrief()
  } catch (e) {
    if (e instanceof ApiError && e.code === 'NO_BRIEF') {
      noBrief.value = true
    } else {
      errorMessage.value = e instanceof Error ? e.message : '加载失败，请稍后重试。'
    }
  } finally {
    loading.value = false
  }
}

async function loadDate(date: string) {
  loading.value = true
  errorMessage.value = ''
  try {
    brief.value = await getBriefByDate(date)
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : '加载失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

function goNewer() {
  if (!hasNewer.value) return
  loadDate(availableDates.value[currentIndex.value - 1])
}

function goOlder() {
  if (!hasOlder.value) return
  loadDate(availableDates.value[currentIndex.value + 1])
}

function handleDateSelect(value: unknown) {
  loadDate(String(value))
}

function formatMeta(value: string) {
  return dayjs(value).format('YYYY-MM-DD HH:mm')
}

function formatDate(value: string) {
  return dayjs(value).format('YYYY年M月D日')
}

function formatCitationTime(value: string | null) {
  return value ? dayjs(value).format('YYYY-MM-DD') : '发布时间未知'
}

onMounted(() => {
  loadDateList()
  loadLatest()
})
</script>

<template>
  <section class="brief-view">
    <LoadingPanel v-if="loading" tip="加载简报中…" />
    <ErrorState v-else-if="errorMessage" :message="errorMessage" @retry="loadLatest" />
    <EmptyState
      v-else-if="noBrief"
      title="还没有生成过简报"
      description="等下一次抽取跑完，这里会出现每日简报。"
    />

    <template v-else-if="brief">
      <header class="brief-view__header">
        <div class="brief-view__date-nav">
          <button
            type="button"
            class="brief-view__nav-btn"
            :disabled="!hasOlder"
            title="更早一期"
            @click="goOlder"
          >
            ← 更早
          </button>
          <a-select
            :value="brief.date"
            class="brief-view__date-select"
            :options="availableDates.map((date) => ({ value: date, label: formatDate(date) }))"
            @change="handleDateSelect"
          />
          <button
            type="button"
            class="brief-view__nav-btn"
            :disabled="!hasNewer"
            title="更新一期"
            @click="goNewer"
          >
            更新 →
          </button>
        </div>

        <h1 class="brief-view__title">{{ brief.title }}</h1>
        <p class="brief-view__meta mono">
          本简报由 {{ brief.model_name }} 于 {{ formatMeta(brief.created_at) }} 自动生成 ·
          {{ formatDate(brief.date) }}
        </p>
      </header>

      <!-- eslint-disable-next-line vue/no-v-html -->
      <div class="brief-view__content" v-html="renderedContent"></div>

      <footer v-if="brief.citations.length" class="brief-view__references">
        <h2 class="brief-view__references-title">参考文献</h2>
        <ol class="brief-view__reference-list">
          <li
            v-for="citation in brief.citations"
            :id="`cite-${citation.index}`"
            :key="citation.index"
            class="brief-view__reference"
          >
            <span class="brief-view__reference-index mono">[{{ citation.index }}]</span>
            <a
              class="brief-view__reference-title"
              :href="citation.url"
              target="_blank"
              rel="noopener noreferrer"
            >
              {{ citation.title }}
            </a>
            <span class="brief-view__reference-time mono">{{
              formatCitationTime(citation.publish_time)
            }}</span>
          </li>
        </ol>
      </footer>
    </template>
  </section>
</template>

<style scoped lang="scss">
.brief-view {
  max-width: 760px;
  margin: 0 auto;
  padding: var(--space-6) var(--space-5) var(--space-8);
}

.brief-view__header {
  border-bottom: 1px solid var(--color-border);
  padding-bottom: var(--space-5);
  margin-bottom: var(--space-6);
}

.brief-view__date-nav {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.brief-view__nav-btn {
  background: none;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  padding: 4px var(--space-3);
  font-size: 12px;
  color: var(--color-text-muted);
  cursor: pointer;

  &:hover:not(:disabled) {
    border-color: var(--color-accent);
    color: var(--color-accent-strong);
  }

  &:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
}

.brief-view__date-select {
  width: 180px;
}

.brief-view__title {
  font-size: 28px;
  margin-bottom: var(--space-2);
}

.brief-view__meta {
  font-size: 12px;
  color: var(--color-text-muted);
  margin: 0;
}

.brief-view__content {
  font-size: 15px;
  line-height: 1.9;
  color: var(--color-text);

  :deep(h1),
  :deep(h2),
  :deep(h3) {
    margin: var(--space-6) 0 var(--space-3);
  }

  :deep(p) {
    margin: 0 0 var(--space-4);
  }

  :deep(ul),
  :deep(ol) {
    margin: 0 0 var(--space-4);
    padding-left: 1.4em;
  }

  :deep(li) {
    margin-bottom: var(--space-1);
  }

  :deep(.cite) {
    color: var(--color-accent-strong);
    font-weight: 600;
    text-decoration: none;
    padding: 0 2px;

    &:hover {
      text-decoration: underline;
    }
  }
}

.brief-view__references {
  margin-top: var(--space-7);
  padding-top: var(--space-5);
  border-top: 1px solid var(--color-border);
}

.brief-view__references-title {
  font-size: 16px;
  margin-bottom: var(--space-3);
}

.brief-view__reference-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.brief-view__reference {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  font-size: 13px;
  scroll-margin-top: var(--space-5);
  padding: var(--space-1) 0;
}

.brief-view__reference-index {
  color: var(--color-accent-strong);
  flex-shrink: 0;
}

.brief-view__reference-title {
  color: var(--color-text);
  text-decoration: none;
  flex: 1;

  &:hover {
    color: var(--color-accent-strong);
    text-decoration: underline;
  }
}

.brief-view__reference-time {
  color: var(--color-text-muted);
  flex-shrink: 0;
}
</style>
