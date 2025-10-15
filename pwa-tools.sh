#!/bin/bash
# Script de comandos úteis para gerenciar PWA do GRIS

echo "🚀 GRIS PWA - Comandos Úteis"
echo "=============================="
echo ""

# Cores
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Função para executar comandos
run_command() {
    echo -e "${BLUE}Executando:${NC} $1"
    eval $1
    echo ""
}

case "$1" in
    build)
        echo -e "${GREEN}📦 Buildando assets do GRIS...${NC}"
        run_command "cd /workspace/frappe-bench && bench build --app gris"
        ;;
    
    restart)
        echo -e "${GREEN}🔄 Reiniciando servidor...${NC}"
        run_command "cd /workspace/frappe-bench && bench restart"
        ;;
    
    rebuild)
        echo -e "${GREEN}🔨 Rebuild completo (build + restart)...${NC}"
        run_command "cd /workspace/frappe-bench && bench build --app gris"
        run_command "cd /workspace/frappe-bench && bench restart"
        ;;
    
    icons)
        echo -e "${GREEN}🎨 Gerando ícones placeholder...${NC}"
        run_command "cd /workspace/frappe-bench/apps/gris/gris/public/images && python3 create_placeholders.py"
        ;;
    
    clear-cache)
        echo -e "${YELLOW}⚠️  Para limpar cache do browser:${NC}"
        echo "1. Abra DevTools (F12)"
        echo "2. Application → Storage → Clear site data"
        echo "3. Ou use Ctrl+Shift+Delete"
        echo ""
        echo "Para desregistrar Service Worker:"
        echo "1. DevTools (F12) → Application"
        echo "2. Service Workers → Unregister"
        ;;
    
    check)
        echo -e "${GREEN}🔍 Verificando arquivos PWA...${NC}"
        echo ""
        echo "📄 Manifest:"
        ls -lh /workspace/frappe-bench/apps/gris/gris/public/manifest.json 2>/dev/null && echo "  ✅ Existe" || echo "  ❌ Não encontrado"
        
        echo ""
        echo "🔧 Service Worker:"
        ls -lh /workspace/frappe-bench/apps/gris/gris/public/js/service-worker.js 2>/dev/null && echo "  ✅ Existe" || echo "  ❌ Não encontrado"
        
        echo ""
        echo "⚙️  PWA Init:"
        ls -lh /workspace/frappe-bench/apps/gris/gris/public/js/pwa-init.js 2>/dev/null && echo "  ✅ Existe" || echo "  ❌ Não encontrado"
        
        echo ""
        echo "🎨 Ícones:"
        icon_count=$(ls /workspace/frappe-bench/apps/gris/gris/public/images/icons/*.svg 2>/dev/null | wc -l)
        if [ $icon_count -eq 8 ]; then
            echo "  ✅ $icon_count ícones encontrados"
        else
            echo "  ⚠️  $icon_count ícones (esperado: 8)"
        fi
        
        echo ""
        echo "📱 Template Head:"
        ls -lh /workspace/frappe-bench/apps/gris/gris/templates/includes/pwa_head.html 2>/dev/null && echo "  ✅ Existe" || echo "  ❌ Não encontrado"
        ;;
    
    logs)
        echo -e "${GREEN}📋 Verificando logs do servidor...${NC}"
        run_command "cd /workspace/frappe-bench && tail -n 50 logs/web.dev.log"
        ;;
    
    url)
        echo -e "${GREEN}🌐 URLs para testar PWA:${NC}"
        echo ""
        echo "Local: http://localhost:8000"
        echo "Dev: https://dev.gris"
        echo ""
        echo "Para testar manifest:"
        echo "http://localhost:8000/assets/gris/manifest.json"
        echo ""
        echo "Para testar Service Worker:"
        echo "http://localhost:8000/assets/gris/js/service-worker.js"
        ;;
    
    devtools)
        echo -e "${GREEN}🛠️  Como verificar PWA no DevTools:${NC}"
        echo ""
        echo "1. Abra o site"
        echo "2. Pressione F12"
        echo "3. Vá para aba 'Application'"
        echo ""
        echo "Verifique:"
        echo "  ✓ Manifest - deve carregar sem erros"
        echo "  ✓ Service Workers - status 'activated and running'"
        echo "  ✓ Cache Storage - deve ter 'gris-cache-v1'"
        echo ""
        echo "Para audit Lighthouse:"
        echo "1. DevTools → Lighthouse"
        echo "2. Selecione 'Progressive Web App'"
        echo "3. Click 'Generate report'"
        ;;
    
    install)
        echo -e "${GREEN}📱 Como instalar o PWA:${NC}"
        echo ""
        echo "Desktop (Chrome/Edge):"
        echo "  • Procure ícone ➕ na barra de endereço"
        echo "  • Ou: Menu → Instalar GRIS"
        echo ""
        echo "Android (Chrome):"
        echo "  • Menu (⋮) → 'Instalar app'"
        echo "  • Ou: Popup automático após algumas visitas"
        echo ""
        echo "iOS (Safari):"
        echo "  • Botão Compartilhar → 'Adicionar à Tela de Início'"
        echo "  • (Não há prompt automático no iOS)"
        ;;
    
    test)
        echo -e "${GREEN}🧪 Testando configuração PWA...${NC}"
        echo ""
        
        # Testa manifest
        echo "1. Testando manifest.json..."
        if curl -s http://localhost:8000/assets/gris/manifest.json > /dev/null 2>&1; then
            echo "   ✅ Manifest acessível"
        else
            echo "   ❌ Manifest não encontrado"
        fi
        
        # Testa service worker
        echo ""
        echo "2. Testando service-worker.js..."
        if curl -s http://localhost:8000/assets/gris/js/service-worker.js > /dev/null 2>&1; then
            echo "   ✅ Service Worker acessível"
        else
            echo "   ❌ Service Worker não encontrado"
        fi
        
        # Testa ícones
        echo ""
        echo "3. Testando ícones..."
        if curl -s http://localhost:8000/assets/gris/images/icons/icon-192x192.svg > /dev/null 2>&1; then
            echo "   ✅ Ícone 192x192 acessível"
        else
            echo "   ❌ Ícone 192x192 não encontrado"
        fi
        ;;
    
    *)
        echo "Uso: $0 {comando}"
        echo ""
        echo "Comandos disponíveis:"
        echo ""
        echo "  ${GREEN}build${NC}        - Builda os assets do GRIS"
        echo "  ${GREEN}restart${NC}      - Reinicia o servidor"
        echo "  ${GREEN}rebuild${NC}      - Build + restart"
        echo "  ${GREEN}icons${NC}        - Gera ícones placeholder"
        echo "  ${GREEN}clear-cache${NC}  - Instruções para limpar cache"
        echo "  ${GREEN}check${NC}        - Verifica arquivos PWA"
        echo "  ${GREEN}logs${NC}         - Mostra logs do servidor"
        echo "  ${GREEN}url${NC}          - Mostra URLs para teste"
        echo "  ${GREEN}devtools${NC}     - Instruções DevTools"
        echo "  ${GREEN}install${NC}      - Instruções de instalação"
        echo "  ${GREEN}test${NC}         - Testa configuração PWA"
        echo ""
        echo "Exemplos:"
        echo "  $0 rebuild"
        echo "  $0 check"
        echo "  $0 test"
        ;;
esac
