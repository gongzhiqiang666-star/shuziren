"""Exercise build, deploy, upgrade, rollback and data restore in a fresh directory."""
import argparse
import json
from pathlib import Path
import tempfile

from scripts.console_package import build, restore_data_backup, switch_release, verify_data_backup
from scripts.local_console_config import ConfigStore
from scripts.product_store import ProductStore


def validate(root, base_revision, target_revision):
    root = root.resolve()
    if root.exists():
        raise FileExistsError(f'validation root must be unused: {root}')
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='shuziren-release-packages-') as temporary:
        temporary = Path(temporary)
        base_archive = temporary / 'base.zip'
        target_archive = temporary / 'target.zip'
        base_manifest = build(base_archive, base_revision)
        target_manifest = build(target_archive, target_revision)
        first = switch_release(root, base_archive)
        if first != {'current': base_manifest['commit'], 'previous': None}:
            raise RuntimeError('first deploy pointer mismatch')
        data = root / 'data'
        ConfigStore(data).save({'version': 1, 'port': 5218, 'runtime_root': ''})
        products = ProductStore(data)
        product = products.save(title='升级恢复验证商品', content='升级前内容', product_index=701)
        products.select(product['id'])
        script_id = products.add_script(product, '升级前审核话术')
        products.select_script(product['id'], script_id)

        upgraded = switch_release(root, target_archive)
        if upgraded != {'current': target_manifest['commit'], 'previous': base_manifest['commit']}:
            raise RuntimeError('upgrade pointer mismatch')
        backups_after_upgrade = sorted((root / 'backups').iterdir())
        if len(backups_after_upgrade) != 1:
            raise RuntimeError('upgrade did not create exactly one backup')
        upgrade_backup = backups_after_upgrade[0]
        verify_data_backup(root, upgrade_backup.name)

        rolled_back = switch_release(root)
        if rolled_back != {'current': base_manifest['commit'], 'previous': target_manifest['commit']}:
            raise RuntimeError('rollback pointer mismatch')
        if len(list((root / 'backups').iterdir())) != 2:
            raise RuntimeError('rollback did not create its own backup')

        config = ConfigStore(data).load()
        ConfigStore(data).save({**config, 'port': 5999})
        current = products.get(product['id'])
        products.save(title=current['title'], content='恢复前临时修改', product_index=current['product_index'],
                      product_id=current['id'], version=current['version'])
        restored = restore_data_backup(root, upgrade_backup.name)
        restored_product = ProductStore(data).get(product['id'])
        restored_config = ConfigStore(data).load()
        if restored_product['content'] != '升级前内容' or restored_config['port'] != 5218:
            raise RuntimeError('restored business data differs from pre-upgrade snapshot')
        if ProductStore(data).selected_script(product['id']) != script_id:
            raise RuntimeError('restored product/script selection mismatch')
        active = json.loads((root / 'active.json').read_text(encoding='utf-8'))
        if active != rolled_back:
            raise RuntimeError('data restore unexpectedly changed release pointer')
        safety, _ = verify_data_backup(root, restored['safety_backup'])
        safety_product = ProductStore(safety / 'data').get(product['id'])
        if safety_product['content'] != '恢复前临时修改':
            raise RuntimeError('restore safety backup did not preserve replaced data')
    report = {
        'status': 'passed', 'root': str(root), 'base_commit': base_manifest['commit'],
        'target_commit': target_manifest['commit'], 'active': active,
        'upgrade_backup': upgrade_backup.name, 'restore_safety_backup': restored['safety_backup'],
        'restored_product_id': product['id'], 'restored_script_id': script_id,
        'backup_count': len(list((root / 'backups').iterdir())),
    }
    (root / 'validation-result.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--base-revision', default='HEAD~1')
    parser.add_argument('--target-revision', default='HEAD')
    args = parser.parse_args()
    print(json.dumps(validate(args.root, args.base_revision, args.target_revision), ensure_ascii=False))


if __name__ == '__main__':
    main()
