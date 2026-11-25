#!/usr/bin/env python3
"""
Script para remover todos os diretórios __pycache__ e arquivos .DS_Store recursivamente.
Ignora o diretório .venv durante a busca.
Uso: python clean_pycache.py
"""

import os
import shutil
from pathlib import Path
from typing import List, Tuple

# Diretórios a serem ignorados durante a busca
IGNORED_DIRS = {".venv", "venv", "env", ".env", "node_modules"}


def find_pycache_dirs(root_path: Path) -> List[Path]:
    """
    Encontra todos os diretórios __pycache__ recursivamente, ignorando diretórios específicos.

    Args:
        root_path: Diretório raiz para iniciar a busca

    Returns:
        Lista de caminhos para diretórios __pycache__
    """
    pycache_dirs = []

    for dirpath, dirnames, _ in os.walk(root_path):
        # Remove diretórios ignorados da busca (modifica in-place)
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]

        if "__pycache__" in dirnames:
            pycache_path = Path(dirpath) / "__pycache__"
            pycache_dirs.append(pycache_path)

        if ".pytest_cache" in dirnames:
            pycache_path = Path(dirpath) / ".pytest_cache"
            pycache_dirs.append(pycache_path)

    return pycache_dirs


def find_ds_store_files(root_path: Path) -> List[Path]:
    """
    Encontra todos os arquivos .DS_Store recursivamente, ignorando diretórios específicos.

    Args:
        root_path: Diretório raiz para iniciar a busca

    Returns:
        Lista de caminhos para arquivos .DS_Store
    """
    ds_store_files = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Remove diretórios ignorados da busca (modifica in-place)
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]

        if ".DS_Store" in filenames:
            ds_store_path = Path(dirpath) / ".DS_Store"
            ds_store_files.append(ds_store_path)

    return ds_store_files


def remove_pycache_dirs(pycache_dirs: List[Path]) -> Tuple[int, int]:
    """
    Remove os diretórios __pycache__ encontrados.

    Args:
        pycache_dirs: Lista de diretórios __pycache__ para remover

    Returns:
        Tupla com (total removidos, total com erro)
    """
    removed = 0
    errors = 0

    for pycache_dir in pycache_dirs:
        try:
            shutil.rmtree(pycache_dir)
            print(f"  ✓ Removido: {pycache_dir}")
            removed += 1
        except Exception as e:
            print(f"  ✗ Erro ao remover {pycache_dir}: {e}")
            errors += 1

    return removed, errors


def remove_ds_store_files(ds_store_files: List[Path]) -> Tuple[int, int]:
    """
    Remove os arquivos .DS_Store encontrados.

    Args:
        ds_store_files: Lista de arquivos .DS_Store para remover

    Returns:
        Tupla com (total removidos, total com erro)
    """
    removed = 0
    errors = 0

    for ds_store_file in ds_store_files:
        try:
            ds_store_file.unlink()
            print(f"  ✓ Removido: {ds_store_file}")
            removed += 1
        except Exception as e:
            print(f"  ✗ Erro ao remover {ds_store_file}: {e}")
            errors += 1

    return removed, errors


def main():
    """Função principal do script."""
    print("🔍 Procurando arquivos e diretórios para limpeza...")
    print(f"   (Ignorando: {', '.join(IGNORED_DIRS)})\n")

    # Obtém o diretório atual
    current_dir = Path.cwd()

    # Encontra todos os diretórios __pycache__
    pycache_dirs = find_pycache_dirs(current_dir)

    # Encontra todos os arquivos .DS_Store
    ds_store_files = find_ds_store_files(current_dir)

    total_items = len(pycache_dirs) + len(ds_store_files)

    if total_items == 0:
        print("✅ Nenhum arquivo ou diretório para limpar encontrado!")
        return

    print(f"📦 Encontrados:")
    print(f"   • {len(pycache_dirs)} diretório(s) __pycache__")
    print(f"   • {len(ds_store_files)} arquivo(s) .DS_Store")
    print(f"   • Total: {total_items} item(ns)\n")

    # Lista os itens encontrados
    if pycache_dirs:
        print("📋 Diretórios __pycache__ que serão removidos:")
        for pycache_dir in pycache_dirs:
            relative_path = pycache_dir.relative_to(current_dir)
            print(f"  • {relative_path}")
        print()

    if ds_store_files:
        print("📋 Arquivos .DS_Store que serão removidos:")
        for ds_store_file in ds_store_files:
            relative_path = ds_store_file.relative_to(current_dir)
            print(f"  • {relative_path}")
        print()

    print("🗑️  Removendo itens...\n")

    # Remove os diretórios __pycache__
    pycache_removed = 0
    pycache_errors = 0
    if pycache_dirs:
        print("Removendo diretórios __pycache__:")
        pycache_removed, pycache_errors = remove_pycache_dirs(pycache_dirs)
        print()

    # Remove os arquivos .DS_Store
    ds_store_removed = 0
    ds_store_errors = 0
    if ds_store_files:
        print("Removendo arquivos .DS_Store:")
        ds_store_removed, ds_store_errors = remove_ds_store_files(ds_store_files)
        print()

    # Mostra o resultado
    print("=" * 50)
    print("✨ Limpeza concluída!")
    print(f"  • __pycache__ removidos: {pycache_removed}")
    print(f"  • .DS_Store removidos: {ds_store_removed}")
    print(f"  • Total removidos: {pycache_removed + ds_store_removed}")

    total_errors = pycache_errors + ds_store_errors
    if total_errors > 0:
        print(f"  • Erros: {total_errors}")

    # Verifica se ainda existem itens
    remaining_pycache = find_pycache_dirs(current_dir)
    remaining_ds_store = find_ds_store_files(current_dir)
    remaining_total = len(remaining_pycache) + len(remaining_ds_store)

    if remaining_total > 0:
        print(f"\n⚠️  Ainda existem {remaining_total} item(ns) restante(s):")
        if remaining_pycache:
            print(f"   • {len(remaining_pycache)} diretório(s) __pycache__")
        if remaining_ds_store:
            print(f"   • {len(remaining_ds_store)} arquivo(s) .DS_Store")
        print("   Pode ser necessário executar novamente com permissões adequadas.")
    else:
        print("\n✅ Todos os itens foram removidos com sucesso!")

    print("=" * 50)


if __name__ == "__main__":
    main()
'''
Conexão passa exclusivamente pelo sidecar tsh db proxy em localhost:PORT — sem senha, sem SSL
DatabaseConfig eliminou o campo password; MYSQL_PASSWORD foi removida do .env.example e da documentação
lifespan.py garante SET SESSION TRANSACTION READ ONLY via init_command em todas as conexões do pool
Loopback bypass: quando MYSQL_HOST é 127.0.0.1/localhost, o SSL é ignorado automaticamente (Teleport já criptografa o tunnel)
Testes reforçados: SSL bypass, ausência de senha no pool, repr() mascarado no config
Spec canônico criado em openspec/specs/teleport-db-auth/spec.md
    
    
    '''