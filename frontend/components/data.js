/**
 * 투자거울: 데이터 관리 컴포넌트 (data.js)
 * 날짜별 코스피 및 매매 내역 CRUD, 파일 임포트, 동기화, CSV/JSON 내보내기
 */

const DataComponent = {
  expandedDates: new Set(),

  render(container) {
    const state = window.store.getState();
    const records = state.records || [];

    container.innerHTML = `
      <div class="data-container">
        <div class="data-header">
          <div class="data-title-group">
            <h2>📋 시계열 데이터 관리</h2>
            <p class="data-subtitle">코스피 지수와 날짜별 매매 기록을 등록·수정·삭제하고, 엑셀/CSV 파일로 한 번에 입력하거나 내보낼 수 있습니다.</p>
          </div>
          <div class="data-action-buttons">
            <button id="btn-open-add-modal" class="btn-primary btn-sm">➕ 신규 날짜 추가</button>
            <button id="btn-sync-kospi" class="btn-outline btn-sm">🔄 최신 코스피 불러오기</button>
            <input type="file" id="file-import-input" accept=".csv,.xlsx,.xls" style="display:none;" />
            <button id="btn-import-file" class="btn-outline btn-sm">📂 거래내역 파일 올리기</button>
            <a href="${window.Api.getExportUrl('csv')}" download="investment_mirror_data.csv" class="btn-outline btn-sm">📥 CSV 내보내기</a>
          </div>
        </div>

        <!-- Filter bar -->
        <div class="data-filter-bar">
          <label>기간 필터:</label>
          <input type="date" id="filter-start-date" class="date-input" />
          <span>~</span>
          <input type="date" id="filter-end-date" class="date-input" />
          <button id="btn-apply-filter" class="btn-sm btn-outline">조회</button>
          <button id="btn-reset-filter" class="btn-sm btn-outline">전체</button>
          <span class="total-count-badge">총 <strong>${records.length}</strong>개 거래일</span>
        </div>

        <!-- Table Container -->
        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width: 120px;">거래일</th>
                <th style="width: 110px;">코스피 종가</th>
                <th>메모 / 이슈</th>
                <th style="width: 100px;">매매 내역</th>
                <th style="width: 140px;">관리</th>
              </tr>
            </thead>
            <tbody id="data-table-body">
              ${this.renderRows(records)}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Add Date Modal -->
      <div id="modal-add-date" class="modal" style="display:none;">
        <div class="modal-content">
          <div class="modal-header">
            <h3>신규 날짜 및 코스피 데이터 등록</h3>
            <button class="modal-close" onclick="window.DataComponent.closeModal('modal-add-date')">&times;</button>
          </div>
          <form id="form-add-date">
            <div class="form-group">
              <label>거래일 (YYYY-MM-DD):</label>
              <input type="date" id="add-date-val" required class="form-input" />
            </div>
            <div class="form-group">
              <label>코스피 종가 (pt):</label>
              <input type="number" step="0.01" id="add-value-val" required class="form-input" placeholder="예: 2580.50" />
            </div>
            <div class="form-group">
              <label>메모 (최대 300자):</label>
              <input type="text" id="add-memo-val" maxlength="300" class="form-input" placeholder="그날의 시장 이슈 또는 특이사항" />
            </div>
            <div class="modal-footer">
              <button type="button" class="btn-outline btn-sm" onclick="window.DataComponent.closeModal('modal-add-date')">취소</button>
              <button type="submit" class="btn-primary btn-sm">저장</button>
            </div>
          </form>
        </div>
      </div>

      <!-- Add Trade Modal -->
      <div id="modal-add-trade" class="modal" style="display:none;">
        <div class="modal-content">
          <div class="modal-header">
            <h3>매매 내역 추가 (<span id="target-trade-date"></span>)</h3>
            <button class="modal-close" onclick="window.DataComponent.closeModal('modal-add-trade')">&times;</button>
          </div>
          <form id="form-add-trade">
            <input type="hidden" id="trade-parent-date" />
            <div class="form-row">
              <div class="form-group">
                <label>구분:</label>
                <select id="trade-side-val" class="form-input">
                  <option value="buy">매수 (Buy)</option>
                  <option value="sell">매도 (Sell)</option>
                </select>
              </div>
              <div class="form-group">
                <label>종목명:</label>
                <input type="text" id="trade-name-val" required class="form-input" placeholder="예: 삼성전자" />
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>수량 (주):</label>
                <input type="number" min="1" id="trade-qty-val" required class="form-input" placeholder="10" />
              </div>
              <div class="form-group">
                <label>단가 (원):</label>
                <input type="number" step="10" min="1" id="trade-price-val" required class="form-input" placeholder="70000" />
              </div>
            </div>
            <div class="form-group">
              <label>매매 이유:</label>
              <select id="trade-reason-val" class="form-input">
                <option value="성장성">성장성</option>
                <option value="시장 흐름">시장 흐름</option>
                <option value="가격 하락">가격 하락</option>
                <option value="뉴스·이슈">뉴스·이슈</option>
                <option value="기타">기타</option>
              </select>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn-outline btn-sm" onclick="window.DataComponent.closeModal('modal-add-trade')">취소</button>
              <button type="submit" class="btn-primary btn-sm">추가</button>
            </div>
          </form>
        </div>
      </div>
    `;

    this.bindEvents(container);
  },

  renderRows(records) {
    if (!records || records.length === 0) {
      return `<tr><td colspan="5" class="empty-cell">등록된 데이터가 없습니다.</td></tr>`;
    }

    return records.map((r) => {
      const isExpanded = this.expandedDates.has(r.date);
      const trades = r.trades || [];
      const tradeCount = trades.length;

      let html = `
        <tr class="date-row">
          <td><strong>${r.date}</strong></td>
          <td>${Number(r.value).toFixed(2)} pt</td>
          <td>${r.memo || '<span class="text-muted">-</span>'}</td>
          <td>
            <button class="btn-trade-toggle" onclick="window.DataComponent.toggleTrades('${r.date}')">
              ${tradeCount > 0 ? `매매 ${tradeCount}건 ${isExpanded ? '▲' : '▼'}` : '+ 매매 등록'}
            </button>
          </td>
          <td class="action-cell">
            <button class="btn-icon-action" title="수정" onclick="window.DataComponent.editDatePrompt('${r.date}', ${r.value}, '${(r.memo || '').replace(/'/g, "\\'")}')">✏️</button>
            <button class="btn-icon-action btn-danger" title="삭제" onclick="window.DataComponent.deleteDate('${r.date}')">🗑️</button>
          </td>
        </tr>
      `;

      if (isExpanded) {
        html += `
          <tr class="trades-sub-row">
            <td colspan="5">
              <div class="nested-trades-container">
                <div class="nested-header">
                  <span><strong>${r.date}</strong> 매매 상세 내역</span>
                  <button class="btn-sm btn-primary" onclick="window.DataComponent.openAddTradeModal('${r.date}')">
                    + 매매 추가
                  </button>
                </div>
                ${this.renderTradesList(r.date, trades)}
              </div>
            </td>
          </tr>
        `;
      }

      return html;
    }).join('');
  },

  renderTradesList(dateStr, trades) {
    if (!trades || trades.length === 0) {
      return `<p class="text-muted empty-sub">이 날짜에 등록된 매매 내역이 없습니다.</p>`;
    }

    return `
      <table class="sub-table">
        <thead>
          <tr>
            <th>구분</th>
            <th>종목명(코드)</th>
            <th>수량</th>
            <th>단가</th>
            <th>매매 이유</th>
            <th>기록 시점</th>
            <th>관리</th>
          </tr>
        </thead>
        <tbody>
          ${trades.map((t) => `
            <tr>
              <td><span class="pill-sm ${t.side === 'buy' ? 'side-buy' : 'side-sell'}">${t.side === 'buy' ? '매수' : '매도'}</span></td>
              <td><strong>${t.name}</strong> (${t.code})</td>
              <td>${t.qty}주</td>
              <td>${Number(t.price).toLocaleString()}원</td>
              <td>${t.reason || '미기재'}</td>
              <td><span class="badge-timing">${t.reason_timing || '당시 기록'}</span></td>
              <td>
                <button class="btn-icon-action btn-danger" title="삭제" onclick="window.DataComponent.deleteTrade('${dateStr}', '${t.id}')">🗑️</button>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  },

  bindEvents(container) {
    // Open Add Date modal
    const openAddBtn = container.querySelector('#btn-open-add-modal');
    if (openAddBtn) {
      openAddBtn.addEventListener('click', () => {
        document.getElementById('modal-add-date').style.display = 'flex';
      });
    }

    // Add Date form submission
    const formAddDate = container.querySelector('#form-add-date');
    if (formAddDate) {
      formAddDate.addEventListener('submit', async (e) => {
        e.preventDefault();
        const dateVal = document.getElementById('add-date-val').value;
        const valueVal = parseFloat(document.getElementById('add-value-val').value);
        const memoVal = document.getElementById('add-memo-val').value;

        try {
          await window.Api.createData({ date: dateVal, value: valueVal, memo: memoVal });
          this.closeModal('modal-add-date');
          alert('✅ 신규 날짜 데이터가 성공적으로 등록되었습니다.');
          window.Main.refreshData();
        } catch (err) {
          alert(`등록 실패: ${err.message}`);
        }
      });
    }

    // Add Trade form submission
    const formAddTrade = container.querySelector('#form-add-trade');
    if (formAddTrade) {
      formAddTrade.addEventListener('submit', async (e) => {
        e.preventDefault();
        const parentDate = document.getElementById('trade-parent-date').value;
        const sideVal = document.getElementById('trade-side-val').value;
        const nameVal = document.getElementById('trade-name-val').value.trim();
        const qtyVal = parseInt(document.getElementById('trade-qty-val').value);
        const priceVal = parseFloat(document.getElementById('trade-price-val').value);
        const reasonVal = document.getElementById('trade-reason-val').value;

        try {
          await window.Api.addTrade(parentDate, {
            side: sideVal,
            name: nameVal,
            code: "005930",
            qty: qtyVal,
            price: priceVal,
            reason: reasonVal,
            reason_timing: "당시 기록"
          });
          this.closeModal('modal-add-trade');
          alert('✅ 매매 내역이 성공적으로 추가되었습니다.');
          window.Main.refreshData();
        } catch (err) {
          alert(`추가 실패: ${err.message}`);
        }
      });
    }

    // Sync button
    const syncBtn = container.querySelector('#btn-sync-kospi');
    if (syncBtn) {
      syncBtn.addEventListener('click', async () => {
        syncBtn.disabled = true;
        syncBtn.innerText = '동기화 중...';
        try {
          const res = await window.Api.syncMarketData();
          alert(`✅ ${res.message}`);
          window.Main.refreshData();
        } catch (err) {
          alert(`동기화 실패: ${err.message}`);
        } finally {
          syncBtn.disabled = false;
          syncBtn.innerText = '🔄 최신 코스피 불러오기';
        }
      });
    }

    // Import file button
    const importBtn = container.querySelector('#btn-import-file');
    const fileInput = container.querySelector('#file-import-input');
    if (importBtn && fileInput) {
      importBtn.addEventListener('click', () => fileInput.click());
      fileInput.addEventListener('change', async (e) => {
        if (e.target.files && e.target.files[0]) {
          await this.handleFileImport(e.target.files[0]);
          fileInput.value = '';
        }
      });
    }

    // Filter handlers
    const startInput = container.querySelector('#filter-start-date');
    const endInput = container.querySelector('#filter-end-date');
    const applyFilter = container.querySelector('#btn-apply-filter');
    const resetFilter = container.querySelector('#btn-reset-filter');

    if (applyFilter) {
      applyFilter.addEventListener('click', async () => {
        const s = startInput.value;
        const e = endInput.value;
        const records = await window.Api.getDataList(s, e);
        window.store.setState({ records });
        this.updateTableBody();
      });
    }

    if (resetFilter) {
      resetFilter.addEventListener('click', async () => {
        startInput.value = '';
        endInput.value = '';
        const records = await window.Api.getDataList();
        window.store.setState({ records });
        this.updateTableBody();
      });
    }
  },

  async handleFileImport(file) {
    try {
      const candidates = await window.Api.importTradeFile(file);
      if (!candidates || candidates.length === 0) {
        alert('파일에서 인식 가능한 매매 내역을 찾지 못했습니다.');
        return;
      }

      const newTrades = candidates.filter(c => !c.is_already_saved);
      const dupCount = candidates.length - newTrades.length;

      if (confirm(`총 ${candidates.length}건 중 신규 매매 ${newTrades.length}건을 등록하시겠습니까? (중복 제외: ${dupCount}건)`)) {
        for (const t of newTrades) {
          await window.Api.addTrade(t.date, t);
        }
        alert(`✅ ${newTrades.length}건의 매매가 성공적으로 등록되었습니다.`);
        window.Main.refreshData();
      }
    } catch (err) {
      alert(`파일 임포트 실패: ${err.message}`);
    }
  },

  toggleTrades(dateStr) {
    if (this.expandedDates.has(dateStr)) {
      this.expandedDates.delete(dateStr);
    } else {
      this.expandedDates.add(dateStr);
    }
    this.updateTableBody();
  },

  updateTableBody() {
    const tbody = document.getElementById('data-table-body');
    if (tbody) {
      const state = window.store.getState();
      tbody.innerHTML = this.renderRows(state.records || []);
    }
  },

  openAddTradeModal(dateStr) {
    document.getElementById('target-trade-date').innerText = dateStr;
    document.getElementById('trade-parent-date').value = dateStr;
    document.getElementById('modal-add-trade').style.display = 'flex';
  },

  closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.style.display = 'none';
  },

  async editDatePrompt(dateStr, currentVal, currentMemo) {
    const newValStr = prompt(`${dateStr} 코스피 종가 수정:`, currentVal);
    if (newValStr === null) return;
    const newVal = parseFloat(newValStr);
    if (isNaN(newVal) || newVal <= 0) {
      alert('0보다 큰 유효한 숫자를 입력해 주세요.');
      return;
    }

    const newMemo = prompt(`${dateStr} 메모 수정:`, currentMemo);
    if (newMemo === null) return;

    try {
      await window.Api.updateData(dateStr, { value: newVal, memo: newMemo });
      alert('✅ 수정되었습니다.');
      window.Main.refreshData();
    } catch (err) {
      alert(`수정 실패: ${err.message}`);
    }
  },

  async deleteDate(dateStr) {
    if (!confirm(`${dateStr} 날짜의 데이터와 해당 날짜의 모든 매매 기록을 삭제하시겠습니까?`)) {
      return;
    }
    try {
      await window.Api.deleteData(dateStr);
      alert('✅ 삭제되었습니다.');
      window.Main.refreshData();
    } catch (err) {
      alert(`삭제 실패: ${err.message}`);
    }
  },

  async deleteTrade(dateStr, tradeId) {
    if (!confirm('이 매매 내역을 삭제하시겠습니까?')) return;
    try {
      await window.Api.deleteTrade(dateStr, tradeId);
      alert('✅ 매매가 삭제되었습니다.');
      window.Main.refreshData();
    } catch (err) {
      alert(`삭제 실패: ${err.message}`);
    }
  }
};

window.DataComponent = DataComponent;
