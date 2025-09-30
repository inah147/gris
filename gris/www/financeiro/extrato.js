// Paginação do extrato (similar ao contribuições)
function renderExtratoPagination(container, totalPages, current, buildUrl) {
	// Limpa qualquer conteúdo anterior para evitar duplicidade
	container.innerHTML = '';
	const ul = document.createElement('ul');
	ul.className = 'pagination pagination-sm mb-0';
	const addItem = (label, page, disabled=false, active=false) => {
		const li = document.createElement('li');
		li.className = 'page-item' + (disabled? ' disabled':'') + (active? ' active':'');
		const a = document.createElement('a');
		a.className = 'page-link';
		a.textContent = label;
		if(!disabled && !active){
			a.href = buildUrl(page);
		}
		li.appendChild(a);
		ul.appendChild(li);
	};
	addItem('«', 1, current===1);
	addItem('‹', current-1, current===1);
	const windowSize = 5;
	let start = Math.max(1, current - Math.floor(windowSize/2));
	let end = start + windowSize -1;
	if(end > totalPages){
		end = totalPages;
		start = Math.max(1, end - windowSize +1);
	}
	for(let p = start; p<=end; p++) addItem(String(p), p, false, p===current);
	addItem('›', current+1, current===totalPages);
	addItem('»', totalPages, current===totalPages);
	container.appendChild(ul);
}

document.addEventListener('DOMContentLoaded', function() {
	const pagDiv = document.getElementById('extrato-pagination');
	if(!pagDiv) return;
	const total = parseInt(pagDiv.dataset.total, 10);
	const page = parseInt(pagDiv.dataset.page, 10);
	const pageSize = parseInt(pagDiv.dataset.pagesize, 10);
	const totalPages = Math.ceil(total / pageSize);
	if(totalPages <= 1) return;
	function buildUrl(p) {
		const params = new URLSearchParams(window.location.search);
		params.set('page', p);
		return window.location.pathname + '?' + params.toString();
	}
	renderExtratoPagination(pagDiv, totalPages, page, buildUrl);
});
