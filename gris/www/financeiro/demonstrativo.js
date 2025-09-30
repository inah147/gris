// JS for Demonstrativo Financeiro - stub for future interactions (year picker, export)
document.addEventListener('DOMContentLoaded', function () {
  var ano = document.getElementById('ano');
  if (ano) {
    ano.addEventListener('change', function () {
      var form = document.getElementById('demonstrativo-filter');
      if (form) form.submit();
    });
  }
});
