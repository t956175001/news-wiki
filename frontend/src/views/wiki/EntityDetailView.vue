<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <section class="placeholder">
    <h1>词条详情</h1>
    <p>
      占位页面，内容见 D9。实体 id：<span class="mono">{{ route.params.id }}</span>
    </p>
  </section>
</template>
