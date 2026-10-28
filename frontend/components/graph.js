/**
 * 투자거울: 그래프 컴포넌트 (graph.js)
 * 기간 첫 거래일을 100으로 맞춘 코스피·종목 정규화 비교 선 및 매수·매도 포인트 시각화 (순수 HTML5 Canvas 구현)
 */

const GraphComponent = {
  render(container) {
    const state = window.store.getState();
    const stocks = [
      { name: "삼성전자", code: "005930" },
      { name: "SK하이닉스", code: "000660" },
      { name: "NAVER", code: "035420" },
      { name: "카카오", code: "035720" },
      { name: "현대차", code: "005380" },
      { name: "셀트리온", code: "068270" }
    ];

    container.innerHTML = `
      <div class="graph-container">
        <div class="graph-header">
          <div class="graph-title-group">
            <h2>📈 투자거울 비교 그래프</h2>
            <p class="graph-subtitle">기간 첫 거래일을 100으로 정규화하여 시장(코스피)과 종목의 흐름 위에 내 매매 위치를 비춰 봅니다.</p>
          </div>
          <div class="graph-controls">
            <label for="select-stock">종목 선택:</label>
            <select id="select-stock" class="select-input">
              ${stocks.map(s => `
                <option value="${s.code}" ${s.code === state.selectedStockCode ? 'selected' : ''}>
                  ${s.name} (${s.code})
                </option>
              `).join('')}
            </select>
            <button id="btn-refresh-graph" class="btn-outline btn-sm">다시 그리기</button>
          </div>
        </div>

        <!-- Canvas Chart Area -->
        <div class="canvas-wrapper">
          <canvas id="mirror-canvas" width="860" height="420"></canvas>
          <div id="chart-tooltip" class="chart-tooltip" style="display:none;"></div>
        </div>

        <!-- Legend and Trade Details -->
        <div class="graph-footer">
          <div class="graph-legend">
            <span class="legend-item"><span class="legend-color kospi-color"></span> 코스피 (KOSPI) [기준=100]</span>
            <span class="legend-item"><span class="legend-color stock-color"></span> 개별 종목 [기준=100]</span>
            <span class="legend-item"><span class="legend-dot buy-dot"></span> 매수 지점</span>
            <span class="legend-item"><span class="legend-dot sell-dot"></span> 매도 지점</span>
          </div>
          <div id="trade-marker-info" class="trade-marker-info">
            💡 차트 상의 빨간색(매수) 또는 파란색(매도) 원을 클릭하면 당시의 매매 정보와 이유를 확인할 수 있습니다.
          </div>
        </div>
      </div>
    `;

    this.bindEvents(container);
    this.loadAndDrawChart();
  },

  bindEvents(container) {
    const select = container.querySelector('#select-stock');
    const refreshBtn = container.querySelector('#btn-refresh-graph');

    select.addEventListener('change', (e) => {
      window.store.setState({ selectedStockCode: e.target.value });
      this.loadAndDrawChart();
    });

    refreshBtn.addEventListener('click', () => {
      this.loadAndDrawChart();
    });
  },

  async loadAndDrawChart() {
    const state = window.store.getState();
    const code = state.selectedStockCode || '005930';

    try {
      const data = await window.Api.getStockPrices(code);
      window.store.setState({ stockGraphData: data });
      this.drawCanvas(data);
    } catch (err) {
      console.error("Failed to load stock graph data:", err);
    }
  },

  drawCanvas(stockData) {
    const canvas = document.getElementById('mirror-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    // Clear
    ctx.clearRect(0, 0, width, height);

    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)';
    const textColor = isDark ? '#94a3b8' : '#64748b';
    const kospiLineColor = '#94a3b8'; // Neutral gray
    const stockLineColor = '#3b82f6'; // Bright blue

    const padding = { top: 30, right: 40, bottom: 50, left: 55 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    const points = stockData.data || [];
    if (points.length < 2) {
      ctx.fillStyle = textColor;
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('표시할 시계열 데이터가 부족합니다.', width / 2, height / 2);
      return;
    }

    // Find min and max indexed values
    let minVal = Infinity;
    let maxVal = -Infinity;

    points.forEach((p) => {
      minVal = Math.min(minVal, p.stock_indexed, p.kospi_indexed);
      maxVal = Math.max(maxVal, p.stock_indexed, p.kospi_indexed);
    });

    // Add 5% margin
    const margin = (maxVal - minVal) * 0.08 || 5;
    minVal = Math.floor(minVal - margin);
    maxVal = Math.ceil(maxVal + margin);

    const getX = (i) => padding.left + (i / (points.length - 1)) * chartW;
    const getY = (val) => padding.top + chartH - ((val - minVal) / (maxVal - minVal)) * chartH;

    // Draw horizontal grid lines & Y labels
    ctx.font = '11px sans-serif';
    ctx.fillStyle = textColor;
    ctx.textAlign = 'right';

    const yStep = Math.max(5, Math.round((maxVal - minVal) / 5));
    for (let v = Math.ceil(minVal / yStep) * yStep; v <= maxVal; v += yStep) {
      const y = getY(v);
      ctx.strokeStyle = v === 100 ? (isDark ? '#e2e8f0' : '#475569') : gridColor;
      ctx.lineWidth = v === 100 ? 1.5 : 1;
      ctx.setLineDash(v === 100 ? [4, 4] : []);
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();

      ctx.fillText(`${v}`, padding.left - 10, y + 4);
    }
    ctx.setLineDash([]);

    // Draw X labels (Dates)
    ctx.textAlign = 'center';
    const xStep = Math.max(1, Math.floor(points.length / 6));
    for (let i = 0; i < points.length; i += xStep) {
      const x = getX(i);
      const dt = points[i].date.substring(5); // MM-DD
      ctx.fillText(dt, x, height - padding.bottom + 20);
    }

    // 1. Draw KOSPI Line
    ctx.strokeStyle = kospiLineColor;
    ctx.lineWidth = 2;
    ctx.beginPath();
    points.forEach((p, idx) => {
      const x = getX(idx);
      const y = getY(p.kospi_indexed);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // 2. Draw Stock Line
    ctx.strokeStyle = stockLineColor;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    points.forEach((p, idx) => {
      const x = getX(idx);
      const y = getY(p.stock_indexed);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // 3. Draw Trade Markers
    const trades = stockData.trades || [];
    this.tradePoints = []; // Cache coordinates for click detection

    trades.forEach((t) => {
      const idx = points.findIndex((p) => p.date === t.date);
      if (idx !== -1) {
        const x = getX(idx);
        const y = getY(points[idx].stock_indexed);

        const isBuy = t.side === 'buy';
        const color = isBuy ? '#ef4444' : '#3b82f6';

        // Outer glow
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(x, y, 6, 0, Math.PI * 2);
        ctx.fill();

        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.stroke();

        this.tradePoints.push({ x, y, trade: t, date: t.date });
      }
    });

    // Add click handler on canvas
    canvas.onclick = (e) => {
      const rect = canvas.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const clickY = e.clientY - rect.top;

      let matched = null;
      for (const pt of this.tradePoints) {
        const dist = Math.hypot(pt.x - clickX, pt.y - clickY);
        if (dist <= 12) {
          matched = pt;
          break;
        }
      }

      const infoBox = document.getElementById('trade-marker-info');
      if (matched && infoBox) {
        const t = matched.trade;
        const sideKr = t.side === 'buy' ? '매수' : '매도';
        infoBox.innerHTML = `
          <div class="active-trade-box">
            <span class="badge ${t.side === 'buy' ? 'badge-buy' : 'badge-sell'}">${sideKr}</span>
            <strong>${matched.date}</strong> ${t.name} ${t.qty}주 @ ${Number(t.price).toLocaleString()}원
            · <em>이유: ${t.reason || '미기재'} (${t.reason_timing || '당시 기록'})</em>
          </div>
        `;
      }
    };
  }
};

window.GraphComponent = GraphComponent;
