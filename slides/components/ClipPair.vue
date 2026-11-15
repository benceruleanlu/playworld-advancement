<script setup lang="ts">
// Two published rollouts side by side. Clips are 480p releases made by the experiment workflow.
const props = defineProps<{
  task: string
  control: string
  treatment: string
  controlLabel?: string
  treatmentLabel?: string
}>()
const base = 'https://github.com/benceruleanlu/playworld-advancement/releases/download/run-'
const src = (exp: string, ext: string) => `${base}${exp}/${props.task}.${ext}`
</script>

<template>
  <figure class="pair">
    <div class="clips">
      <div class="clip">
        <video :src="src(control, 'mp4')" :poster="src(control, 'jpg')" muted controls playsinline preload="none" />
        <div class="label">{{ controlLabel || 'Control' }}: <code>{{ control }}</code></div>
      </div>
      <div class="clip">
        <video :src="src(treatment, 'mp4')" :poster="src(treatment, 'jpg')" muted controls playsinline preload="none" />
        <div class="label">{{ treatmentLabel || 'Treatment' }}: <code>{{ treatment }}</code></div>
      </div>
    </div>
    <figcaption><slot /></figcaption>
  </figure>
</template>

<style scoped>
.pair { margin: 0.6rem 0 0; }
.clips { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.clip video { width: 100%; aspect-ratio: 16 / 9; background: #000; border-radius: 4px; display: block; }
.label { font-size: 0.8rem; margin-top: 0.25rem; }
figcaption { font-size: 0.72rem; line-height: 1.35; margin-top: 0.5rem; opacity: 0.85; }
</style>
