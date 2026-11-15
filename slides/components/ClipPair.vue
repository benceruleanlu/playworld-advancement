<script setup lang="ts">
// Two published rollouts of one task side by side, with one button that restarts and plays both together.
// Clips are 480p releases made by the experiment workflow. Never autoplays.
import { ref } from 'vue'
const props = defineProps<{
  task: string
  control: string
  treatment: string
  controlLabel?: string
  treatmentLabel?: string
  width?: number
}>()
const base = 'https://github.com/benceruleanlu/playworld-advancement/releases/download/run-'
const src = (exp: string, ext: string) => `${base}${exp}/${props.task}.${ext}`
const a = ref<HTMLVideoElement>()
const b = ref<HTMLVideoElement>()
const playing = ref(false)
function toggle() {
  const vids = [a.value, b.value].filter(Boolean) as HTMLVideoElement[]
  if (playing.value) {
    vids.forEach(v => v.pause())
    playing.value = false
    return
  }
  vids.forEach((v) => { v.currentTime = 0 })
  Promise.all(vids.map(v => v.play())).catch(() => {})
  playing.value = true
}
</script>

<template>
  <figure class="pair" :style="width ? { maxWidth: `${width * 2 + 16}px` } : {}">
    <div class="head">
      <span class="task">{{ task }}</span>
      <button type="button" class="sync" @click="toggle">{{ playing ? 'Pause both' : 'Play both from start' }}</button>
    </div>
    <div class="clips">
      <div class="clip">
        <video ref="a" :src="src(control, 'mp4')" :poster="src(control, 'jpg')" muted controls playsinline loop preload="none" />
        <div class="label">{{ controlLabel || 'Control' }} <code>{{ control }}</code></div>
      </div>
      <div class="clip">
        <video ref="b" :src="src(treatment, 'mp4')" :poster="src(treatment, 'jpg')" muted controls playsinline loop preload="none" />
        <div class="label">{{ treatmentLabel || 'Treatment' }} <code>{{ treatment }}</code></div>
      </div>
    </div>
  </figure>
</template>

<style scoped>
.pair { margin: 0; }
.head { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.2rem; font-size: 14px; }
.task { font-weight: 600; }
.sync { font-size: 13px; padding: 1px 8px; border: 1px solid currentColor; border-radius: 4px; background: transparent; color: inherit; cursor: pointer; }
.clips { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.clip video { width: 100%; aspect-ratio: 16 / 9; background: #000; border-radius: 4px; display: block; }
.label { font-size: 13px; margin-top: 2px; line-height: 1.25; }
.label code { font-size: 13px; }
</style>
