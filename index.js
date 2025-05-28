const { createApp } = Vue;

createApp({
  data() {
    return {
      results: [],
      error: null,
    };
  },
  async mounted() {
    const basePath = "./output/";
    try {
      // simulation scenario一覧取得
      const response = await fetch(`${basePath}summary.json`);
      const scenarios = await response.json();

      // 各シナリオのデータを取得
      this.results = await Promise.all(
        scenarios.map(async (name) => ({
          name: name,
          wave: `${basePath}${name}/wave.svg`,
          event: await (await fetch(`${basePath}${name}/event.json`)).json(),
          states: await (await fetch(`${basePath}${name}/states.json`)).json(),
          tx_fifo: await (await fetch(`${basePath}${name}/tx_fifo.json`)).json(),
          rx_fifo: await (await fetch(`${basePath}${name}/rx_fifo.json`)).json(),
        }))
      );
      console.log(this.results);
    } catch (e) {
      this.error = `Failed to load summary.json: ${e.message}`;
      console.error(e);
    }
  },
}).mount("#app");
