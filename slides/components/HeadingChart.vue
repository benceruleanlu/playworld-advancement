<script setup lang="ts">
// End-heading error in degrees, control vs yaw servo (AGENTS.md, "Status against the timeline"). GC022's pair is from the stack run.
const rows = [
  { task: 'GC031', control: 96, servo: 0 },
  { task: 'GC038', control: 96, servo: 49 },
  { task: 'GC036', control: 70, servo: 5.6 },
  { task: 'GC022', control: 45, servo: 1, note: 'stack run' },
  { task: 'GC033', control: 28, servo: 0.3 },
  { task: 'GC012', control: 8, servo: 2 },
]
const max = 100
const pct = (v: number) => `${(v / max) * 100}%`
</script>

<template>
  <figure class="chart" aria-label="End-heading error in degrees, control and yaw servo, six GC tasks">
    <div class="legend"><span class="sw c" /> Control <span class="sw s" /> Yaw servo</div>
    <div v-for="r in rows" :key="r.task" class="row">
      <div class="task">{{ r.task }}<span v-if="r.note" class="note"><br>{{ r.note }}</span></div>
      <div class="bars">
        <div class="bar-line"><div class="bar c" :style="{ width: pct(r.control) }" /><span class="v">{{ r.control }}</span></div>
        <div class="bar-line"><div class="bar s" :style="{ width: pct(r.servo) }" /><span class="v">{{ r.servo }}</span></div>
      </div>
    </div>
    <div class="axis"><div class="ticks"><span style="left: 0%">0</span><span style="left: 50%">50</span><span style="left: 100%">100</span></div></div>
    <figcaption>End-heading error (degrees from the intended heading at the last frame)</figcaption>
  </figure>
</template>

<style scoped>
.chart { margin: 0; font-size: 14px; }
.legend { display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.4rem; }
.sw { display: inline-block; width: 0.8rem; height: 0.8rem; border-radius: 2px; margin-left: 0.6rem; }
.sw:first-child { margin-left: 0; }
.row { display: grid; grid-template-columns: 5.4rem 1fr; align-items: center; margin: 0.18rem 0; }
.task { font-variant-numeric: tabular-nums; }
.bars { border-left: 1px solid currentColor; padding-left: 0; margin-right: 2.4rem; }
.bar-line { display: flex; align-items: center; height: 14px; margin: 1px 0; }
.bar { height: 100%; min-width: 1px; }
.v { margin-left: 0.3rem; font-variant-numeric: tabular-nums; }
.c { background: #8b8b8b; }
.s { background: #2f6fd6; }
.axis { margin: 0.15rem 2.4rem 0 5.4rem; opacity: 0.8; }
.ticks { position: relative; height: 1rem; border-top: 1px solid currentColor; }
.ticks span { position: absolute; top: 0; transform: translateX(-50%); }
.ticks span::before { content: ''; position: absolute; left: 50%; top: -1px; height: 4px; border-left: 1px solid currentColor; }
.note { font-size: 13px; opacity: 0.85; }
figcaption { margin-top: 0.2rem; margin-left: 5.4rem; opacity: 0.85; }
</style>
