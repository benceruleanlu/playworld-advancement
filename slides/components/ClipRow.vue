<script setup lang="ts">
// A row of published rollouts, each with a heading and a one-line label. Never autoplays.
defineProps<{
  items: { exp: string, task: string, head: string, sub: string }[]
}>()
const base = 'https://github.com/benceruleanlu/playworld-advancement/releases/download/run-'
const src = (exp: string, task: string, ext: string) => `${base}${exp}/${task}.${ext}`
</script>

<template>
  <div class="row" :style="{ gridTemplateColumns: `repeat(${items.length}, 1fr)` }">
    <div v-for="it in items" :key="it.exp + it.task" class="clip">
      <div class="head">{{ it.head }}</div>
      <video :src="src(it.exp, it.task, 'mp4')" :poster="src(it.exp, it.task, 'jpg')" muted controls playsinline loop preload="none" />
      <div class="sub">{{ it.sub }}</div>
    </div>
  </div>
</template>

<style scoped>
.row { display: grid; gap: 14px; }
.head { font-size: 15px; font-weight: 600; margin-bottom: 3px; }
.clip video { width: 100%; aspect-ratio: 16 / 9; background: #000; border-radius: 4px; display: block; }
.sub { font-size: 14px; line-height: 1.3; margin-top: 4px; }
.task { font-size: 13px; opacity: 0.8; margin-top: 2px; }
</style>
