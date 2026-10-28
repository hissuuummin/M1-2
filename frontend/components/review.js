/**
 * 투자거울: 복기 컴포넌트 (review.js)
 * 7일·30일이 지난 매매를 묶어 보여주고, 당시 이유와 이후 시장 흐름을 나란히 비교
 */

const ReviewComponent = {
  async render(container) {
    container.innerHTML = `
      <div class="review-container">
        <div class="review-header">
          <h2>🔍 복기할 매매</h2>
          <p class="review-subtitle">
            매매 후 7일과 30일이 지난 거래를 시장(코스피) 지수와 대조하며, 당시 나의 판단 원칙이 맞았는지 돌아봅니다.
          </p>
        </div>

        <div id="review-cards-list" class="review-cards-list">
          <div class="loading-state">복기 대상을 불러오는 중입니다...</div>
        </div>
      </div>
    `;

    try {
      const items = await window.Api.getPendingReviews();
      window.store.setState({ pendingReviews: items });
      this.renderList(container, items);
    } catch (err) {
      container.querySelector('#review-cards-list').innerHTML = `
        <div class="error-state">복기 목록을 불러오지 못했습니다: ${err.message}</div>
      `;
    }
  },

  renderList(container, items) {
    const listEl = container.querySelector('#review-cards-list');
    if (!listEl) return;

    if (!items || items.length === 0) {
      listEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">✨</div>
          <h3>현재 복기할 매매가 없습니다.</h3>
          <p>매매가 기록된 후 7일 또는 30일이 지나면 이곳에 자동으로 복기 카드가 생성됩니다.</p>
          <button class="btn-primary btn-sm" onclick="window.Main.switchTab('chat')">매매 기록하러 가기</button>
        </div>
      `;
      return;
    }

    listEl.innerHTML = items.map((item) => {
      const isBuy = item.side === 'buy';
      const sideKr = isBuy ? '매수' : '매도';
      const changeClass = item.kospi_change > 0 ? 'trend-up' : item.kospi_change < 0 ? 'trend-down' : 'trend-neutral';

      return `
        <div class="review-card" data-trade-id="${item.trade_id}">
          <div class="review-card-header">
            <div class="review-badge ${item.review_type === '7d' ? 'badge-7d' : 'badge-30d'}">
              ${item.review_type === '7d' ? '7일차 복기' : '30일차 복기'} (${item.days_passed}일 경과)
            </div>
            <span class="trade-date">${item.date}</span>
          </div>

          <div class="review-content-grid">
            <div class="review-trade-info">
              <div class="stock-title">
                <span class="side-pill ${isBuy ? 'side-buy' : 'side-sell'}">${sideKr}</span>
                <strong>${item.name}</strong> (${item.code})
              </div>
              <div class="trade-numbers">
                ${item.qty}주 @ ${Number(item.price).toLocaleString()}원
              </div>
              <div class="trade-reason-box">
                <span class="label">당시 기록된 이유:</span>
                <span class="reason-val">${item.reason || '이유 미기재'}</span>
              </div>
            </div>

            <div class="review-market-change">
              <span class="label">그 사이 코스피 지수 변화</span>
              <div class="market-value-row">
                <span class="then-val">${item.kospi_then} pt</span>
                <span class="arrow">&rarr;</span>
                <span class="now-val">${item.kospi_now} pt</span>
              </div>
              <div class="market-diff ${changeClass}">
                ${item.kospi_change > 0 ? '+' : ''}${item.kospi_change}%
              </div>
            </div>
          </div>

          <div class="reflective-question-box">
            <div class="question-header">💭 다시 생각해 볼 질문</div>
            <p class="question-text">${item.suggested_question}</p>
          </div>

          <div class="review-actions">
            <button class="btn-primary btn-sm" onclick="window.ReviewComponent.markDone('${item.trade_id}', '${item.review_type}')">
              ✓ 복기 완료
            </button>
          </div>
        </div>
      `;
    }).join('');
  },

  async markDone(tradeId, reviewType) {
    try {
      await window.Api.completeReview(tradeId, reviewType);
      alert('✅ 복기를 완료했습니다!');
      const items = await window.Api.getPendingReviews();
      window.store.setState({ pendingReviews: items });
      const container = document.getElementById('tab-content');
      this.renderList(container, items);
    } catch (err) {
      alert(`복기 처리 실패: ${err.message}`);
    }
  }
};

window.ReviewComponent = ReviewComponent;
