<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">分块检索</h2>
    </div>

    <div class="filter-bar">
      <a-select
        v-model:value="selectedDatasetIds"
        mode="multiple"
        placeholder="选择知识库（可选）"
        style="min-width: 240px"
        :options="datasetOptions"
        allow-clear
        :max-tag-count="2"
      />
      <a-select
        v-model:value="selectedDocIds"
        mode="multiple"
        placeholder="选择文档（可选）"
        style="min-width: 240px"
        :options="docOptions"
        allow-clear
        :max-tag-count="2"
        :disabled="docLoading"
      />
    </div>

    <div class="search-bar">
      <a-radio-group v-model:value="searchMode" button-style="solid">
        <a-radio-button value="hybrid">混合检索</a-radio-button>
        <a-radio-button value="vector">向量检索</a-radio-button>
        <a-radio-button value="bm25">BM25</a-radio-button>
      </a-radio-group>
      <a-input-number v-model:value="topK" :min="1" :max="50" style="width: 100px" addon-before="Top" />
      <a-input
        v-model:value="question"
        placeholder="输入检索内容"
        @pressEnter="handleRetrieve"
        style="flex: 1"
      />
      <a-button type="primary" :loading="loading" @click="handleRetrieve" :disabled="!question.trim()">
        检索
      </a-button>
    </div>

    <div v-if="result" class="result-meta">
      <span>共 {{ result.total_retrieved }} 条结果</span>
      <span>检索模式: {{ searchMode }}</span>
      <span class="tabular-nums">耗时: {{ result.retrieval_ms.toFixed(0) }}ms</span>
    </div>

    <a-empty v-if="!loading && result && result.chunks.length === 0" description="未找到相关分块" />

    <div class="chunk-list">
      <a-card v-for="chunk in result?.chunks" :key="chunk.metadata.chunk_id" class="chunk-card" size="small">
        <template #title>
          <div class="chunk-card-title">
            <a-tag color="blue">#{{ chunk.rank }}</a-tag>
            <span>{{ chunk.metadata.filename }}</span>
            <span class="chunk-meta">第 {{ chunk.metadata.page }} 页 · {{ chunk.metadata.char_count }} 字</span>
            <router-link :to="`/chunks/${chunk.metadata.chunk_id}`" class="detail-link">详情</router-link>
          </div>
        </template>
        <div class="chunk-scores">
          <a-tag v-if="chunk.scores.vector_score > 0">向量: {{ chunk.scores.vector_score.toFixed(4) }}</a-tag>
          <a-tag v-if="chunk.scores.bm25_score > 0">BM25: {{ chunk.scores.bm25_score.toFixed(4) }}</a-tag>
          <a-tag v-if="chunk.scores.rrf_score != null" color="green">RRF: {{ chunk.scores.rrf_score.toFixed(4) }}</a-tag>
        </div>
        <div class="chunk-text markdown-body" v-html="renderMarkdown(chunk.full_text)"></div>
        <div v-if="chunk.image_urls && chunk.image_urls.length > 0" class="chunk-images">
          <a-image
            v-for="(url, i) in chunk.image_urls"
            :key="i"
            :src="url"
            :width="200"
            :alt="'表格截图 ' + (i + 1)"
          />
        </div>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { useRouter, useRoute } from 'vue-router'
import { retrieveChunks, type RetrieveResponse } from '@/api/retrieve'
import { listDatasets, type DatasetResponse } from '@/api/datasets'
import { listDocuments, type DocumentListItem } from '@/api/documents'
import { renderMarkdown } from '@/utils/markdown'

const router = useRouter()
const route = useRoute()

const question = ref('')
const searchMode = ref<'vector' | 'bm25' | 'hybrid'>('hybrid')
const topK = ref(10)
const loading = ref(false)
const result = ref<RetrieveResponse | null>(null)

const datasets = ref<DatasetResponse[]>([])
const selectedDatasetIds = ref<string[]>([])
const docs = ref<DocumentListItem[]>([])
const selectedDocIds = ref<string[]>([])
const docLoading = ref(false)

const datasetOptions = computed(() =>
  datasets.value.map((ds) => ({ label: ds.name, value: ds.dataset_id }))
)

const docOptions = computed(() =>
  docs.value.map((d) => ({ label: d.filename, value: d.doc_id }))
)

async function fetchDatasets() {
  try {
    const res = await listDatasets({ size: 100 })
    datasets.value = res.items
  } catch (e: unknown) {
    message.error((e as Error).message)
  }
}

async function fetchDocs() {
  if (selectedDatasetIds.value.length === 0) {
    docs.value = []
    return
  }
  docLoading.value = true
  try {
    const allDocs: DocumentListItem[] = []
    for (const dsId of selectedDatasetIds.value) {
      const res = await listDocuments({ dataset_id: dsId, size: 100 })
      allDocs.push(...res.items)
    }
    docs.value = allDocs
  } catch (e: unknown) {
    message.error((e as Error).message)
  } finally {
    docLoading.value = false
  }
}

watch(selectedDatasetIds, () => {
  selectedDocIds.value = []
  fetchDocs()
})

async function handleRetrieve() {
  const q = question.value.trim()
  if (!q || loading.value) return
  loading.value = true
  result.value = null
  try {
    result.value = await retrieveChunks({
      question: q,
      top_k: topK.value,
      search_mode: searchMode.value,
      dataset_ids: selectedDatasetIds.value.length > 0 ? selectedDatasetIds.value : undefined,
      doc_ids: selectedDocIds.value.length > 0 ? selectedDocIds.value : undefined,
    })
  } catch (e: unknown) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

function parseUrlIds(param: string | string[] | undefined): string[] {
  if (!param) return []
  if (Array.isArray(param)) return param
  return [param]
}

onMounted(async () => {
  await fetchDatasets()

  const urlDatasetIds = parseUrlIds(route.query.dataset_ids as string | string[] | undefined)
  const urlDocIds = parseUrlIds(route.query.doc_ids as string | string[] | undefined)

  if (urlDatasetIds.length > 0) {
    selectedDatasetIds.value = urlDatasetIds
    await fetchDocs()
  }
  if (urlDocIds.length > 0) {
    selectedDocIds.value = urlDocIds
  }
})
</script>

<style scoped>
.page-container {
  padding: 24px;
}

.page-header {
  margin-bottom: 24px;
}

.page-title {
  margin: 0;
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.search-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  align-items: center;
}

.result-meta {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  font-size: 13px;
  color: #666;
}

.chunk-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chunk-card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.chunk-meta {
  color: #999;
  font-size: 12px;
}

.detail-link {
  margin-left: auto;
  font-size: 12px;
}

.chunk-scores {
  margin-bottom: 8px;
}

.chunk-text {
  line-height: 1.6;
  font-size: 13px;
  color: #333;
  max-height: 300px;
  overflow-y: auto;
}

.chunk-images {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}
</style>
