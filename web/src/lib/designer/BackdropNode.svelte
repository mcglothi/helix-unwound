<script lang="ts">
  let { data }: { data: { src: string; w: number; h: number } } = $props()
</script>

<img src={data.src} alt="Vehicle layout" style="width:{data.w}px; height:{data.h}px" draggable="false" />

<style>
  img { display: block; object-fit: contain; border-radius: 12px; opacity: .92; pointer-events: none; user-select: none; }
</style>
