#!/bin/bash
# Script de verificação de setup para Linux/macOS
# Verifica se todas as dependências estão instaladas corretamente

set -e

echo "=========================================="
echo "Verificação de Setup - Document Extraction System"
echo "=========================================="
echo ""

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Função para verificar comando
check_command() {
    local cmd=$1
    local name=$2
    local required_version=$3
    
    if command -v $cmd &> /dev/null; then
        local version=$($cmd --version 2>&1 | head -n 1)
        echo -e "${GREEN}✓${NC} $name encontrado: $version"
        return 0
    else
        echo -e "${RED}✗${NC} $name não encontrado"
        return 1
    fi
}

# Função para verificar versão Python
check_python_version() {
    if command -v python3.11 &> /dev/null; then
        local version=$(python3.11 --version 2>&1 | awk '{print $2}')
        echo -e "${GREEN}✓${NC} Python 3.11 encontrado: $version"
        return 0
    elif command -v python3 &> /dev/null; then
        local version=$(python3 --version 2>&1 | awk '{print $2}')
        local major=$(echo $version | cut -d. -f1)
        local minor=$(echo $version | cut -d. -f2)
        
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            echo -e "${GREEN}✓${NC} Python $version encontrado (mínimo 3.10)"
            return 0
        else
            echo -e "${RED}✗${NC} Python $version encontrado, mas requer 3.10+"
            return 1
        fi
    else
        echo -e "${RED}✗${NC} Python não encontrado"
        return 1
    fi
}

# Função para verificar versão Node.js
check_node_version() {
    if command -v node &> /dev/null; then
        local version=$(node --version | sed 's/v//')
        local major=$(echo $version | cut -d. -f1)
        
        if [ "$major" -ge 18 ]; then
            echo -e "${GREEN}✓${NC} Node.js $version encontrado (mínimo 18)"
            return 0
        else
            echo -e "${RED}✗${NC} Node.js $version encontrado, mas requer 18+"
            return 1
        fi
    else
        echo -e "${RED}✗${NC} Node.js não encontrado"
        return 1
    fi
}

# Verificar Python
echo "Verificando Python..."
check_python_version
PYTHON_OK=$?

# Verificar pip
echo "Verificando pip..."
if [ $PYTHON_OK -eq 0 ]; then
    if command -v python3.11 &> /dev/null; then
        check_command "pip3.11" "pip" || check_command "python3.11 -m pip" "pip (via python -m)"
    else
        check_command "pip3" "pip" || check_command "python3 -m pip" "pip (via python -m)"
    fi
else
    echo -e "${YELLOW}⚠${NC}  Pulando verificação de pip (Python não encontrado)"
fi

# Verificar Node.js
echo ""
echo "Verificando Node.js..."
check_node_version
NODE_OK=$?

# Verificar npm
echo "Verificando npm..."
check_command "npm" "npm"
NPM_OK=$?

# Verificar ambiente virtual
echo ""
echo "Verificando ambiente virtual..."
if [ -d "venv" ]; then
    echo -e "${GREEN}✓${NC} Ambiente virtual encontrado (venv/)"
    
    # Verificar se está ativado
    if [ -n "$VIRTUAL_ENV" ]; then
        echo -e "${GREEN}✓${NC} Ambiente virtual ativado: $VIRTUAL_ENV"
    else
        echo -e "${YELLOW}⚠${NC}  Ambiente virtual não está ativado"
        echo "   Execute: source venv/bin/activate"
    fi
else
    echo -e "${YELLOW}⚠${NC}  Ambiente virtual não encontrado"
    echo "   Execute: python3.11 -m venv venv"
fi

# Verificar dependências Python
echo ""
echo "Verificando dependências Python..."
if [ -d "venv" ] && [ -n "$VIRTUAL_ENV" ]; then
    if python3 -c "from src.graph_extractor import GraphSchemaExtractor" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} Módulos Python principais importáveis"
    else
        echo -e "${YELLOW}⚠${NC}  Módulos Python não importáveis"
        echo "   Execute: pip install -r requirements.txt"
    fi
else
    echo -e "${YELLOW}⚠${NC}  Pulando verificação de módulos (venv não ativado)"
fi

# Verificar dependências Node.js
echo ""
echo "Verificando dependências Node.js..."
if [ -d "frontend/node_modules" ]; then
    echo -e "${GREEN}✓${NC} node_modules encontrado em frontend/"
else
    echo -e "${YELLOW}⚠${NC}  node_modules não encontrado"
    echo "   Execute: cd frontend && npm install"
fi

# Verificar arquivos de configuração
echo ""
echo "Verificando arquivos de configuração..."
if [ -f "configs/secrets.yaml" ]; then
    echo -e "${GREEN}✓${NC} configs/secrets.yaml encontrado"
else
    echo -e "${YELLOW}⚠${NC}  configs/secrets.yaml não encontrado (opcional)"
    echo "   Execute: cp configs/secrets.yaml.example configs/secrets.yaml"
fi

# Resumo
echo ""
echo "=========================================="
echo "Resumo"
echo "=========================================="

ERRORS=0

if [ $PYTHON_OK -ne 0 ]; then
    echo -e "${RED}✗${NC} Python não está instalado corretamente"
    ERRORS=$((ERRORS + 1))
fi

if [ $NODE_OK -ne 0 ]; then
    echo -e "${RED}✗${NC} Node.js não está instalado corretamente"
    ERRORS=$((ERRORS + 1))
fi

if [ $NPM_OK -ne 0 ]; then
    echo -e "${RED}✗${NC} npm não está instalado corretamente"
    ERRORS=$((ERRORS + 1))
fi

if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Todas as dependências principais estão instaladas!"
    echo ""
    echo "Próximos passos:"
    echo "  1. Ative o ambiente virtual: source venv/bin/activate"
    echo "  2. Instale dependências Python: pip install -r requirements.txt"
    echo "  3. Instale dependências Node.js: cd frontend && npm install"
    echo "  4. Configure secrets (opcional): cp configs/secrets.yaml.example configs/secrets.yaml"
    exit 0
else
    echo -e "${RED}✗${NC} Encontrados $ERRORS problema(s)"
    echo ""
    echo "Consulte INSTALLATION.md para instruções de instalação"
    exit 1
fi

