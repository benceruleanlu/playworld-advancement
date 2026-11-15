<script setup lang="ts">
// Two published rollouts of one task side by side, with one button that restarts and plays both together.
// Clips are 480p releases made by the experiment workflow. Never autoplays.
import { onMounted, ref } from 'vue'
import { onSlideLeave } from '@slidev/client'
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
let mirroring = false
const vids = () => [a.value, b.value].filter(Boolean) as HTMLVideoElement[]
const other = (v: HTMLVideoElement) => (v === a.value ? b.value : a.value)
// Resolve once the clip can play from its current position (it loads on demand: preload="none").
function ready(v: HTMLVideoElement) {
  if (v.readyState >= 3) return Promise.resolve()
  return new Promise<void>((res) => {
    v.addEventListener('canplay', () => res(), { once: true })
    v.preload = 'auto'
    if (v.networkState === HTMLMediaElement.NETWORK_EMPTY) v.load()
  })
}
function pauseBoth() {
  mirroring = true
  vids().forEach(v => v.pause())
  playing.value = false
  setTimeout(() => { mirroring = false }, 100)
}
// Start both only once both have data, so a slow first load cannot put them out of step.
async function playBoth(from?: number) {
  const vs = vids()
  mirroring = true
  vs.forEach(v => v.pause())
  await Promise.all(vs.map(ready))
  const t = from ?? vs[0].currentTime
  vs.forEach((v) => { v.currentTime = t })
  await Promise.all(vs.map(v => v.play().catch(() => {})))
  setTimeout(() => { mirroring = false }, 100)
  playing.value = true
}
function toggle() {
  if (playing.value) pauseBoth()
  else playBoth(0)
}
onMounted(() => {
  // Mirror the native controls: pause, play and seek on one clip apply to both.
  vids().forEach((v) => {
    v.addEventListener('pause', () => { if (!mirroring) pauseBoth() })
    v.addEventListener('play', () => { if (!mirroring) playBoth(v.currentTime) })
    v.addEventListener('seeked', () => {
      const o = other(v)
      if (!mirroring && o && Math.abs(o.currentTime - v.currentTime) > 0.1) o.currentTime = v.currentTime
    })
    v.addEventListener('timeupdate', () => {
      const o = other(v)
      if (!mirroring && v === a.value && o && !o.paused && Math.abs(o.currentTime - v.currentTime) > 0.15) o.currentTime = v.currentTime
    })
  })
})
onSlideLeave(() => { if (playing.value || vids().some(v => !v.paused)) pauseBoth() })
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
        <div class="label">{{ controlLabel || 'Control' }}</div>
      </div>
      <div class="clip">
        <video ref="b" :src="src(treatment, 'mp4')" :poster="src(treatment, 'jpg')" muted controls playsinline loop preload="none" />
        <div class="label">{{ treatmentLabel || 'Treatment' }}</div>
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
.label { font-size: 14px; margin-top: 2px; line-height: 1.25; }
.label code { display: block; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
