"""V02-05 real-service probe. Successful transport still requires human review."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import uuid

from scripts.console_llm import LLMError, environment_config
from scripts.llm_tasks import LLMTasks
from scripts.product_store import ProductStore

PRODUCTS = (
    {'product_index':'008', 'title':'验收青瓷杯', 'content':'容量310毫升；材质青瓷；颜色青绿色。未提供价格或优惠。'},
    {'product_index':3, 'title':'验收亚麻桌布', 'content':'尺寸85厘米乘135厘米；材质亚麻；颜色米白色。未提供价格或优惠。'},
)


def run(report_directory, prepare_only=False):
    # Each invocation gets an isolated database; never reuses operator products.
    root=Path(report_directory)/('run-'+uuid.uuid4().hex)
    root.mkdir(parents=True)
    report={'task':'V02-05','status':'prepared','scope':'real-service-generation-awaiting-human-review',
            'real_requests_started':False,'results':[], 'human_review':'pending'}
    manager=None
    try:
        store=ProductStore(root)
        products=[store.save(**value) for value in PRODUCTS]
        report['products']=products
        if prepare_only:
            report['status']='prepared-no-network'
            return report,root,0
        config=environment_config()
        if any(marker in config['model'].lower() for marker in ('fixture','protocol-test')):
            raise LLMError('协议测试模型不得用于V02-05真实验收')
        report['model']=config['model']
        manager=LLMTasks(store)
        instructions='只用本商品已提供的事实写中文口播，80至150字；不编造价格、优惠、库存、服务承诺或个人经历。'
        for product in products:
            manager.start(product['id'],product['version'],instructions)
            report['real_requests_started']=True
            deadline=time.monotonic()+260
            while time.monotonic()<deadline:
                state=manager.state()
                if state['status']!='running': break
                time.sleep(.1)
            else:
                manager.cancel(manager.state()['id'])
                raise LLMError('真实验收等待超时，已取消本地任务')
            if state['status']!='succeeded':
                raise LLMError('真实生成未成功，请检查服务及任务记录')
            scripts=store.scripts(product['id'])
            if len(scripts)!=1 or scripts[0]['snapshot']!=product:
                raise LLMError('话术数量或商品快照不符合要求')
            script=scripts[0]
            if '协议测试文本' in script['text']:
                raise LLMError('发现协议测试输出，不计作真实生成')
            report['results'].append({'product_id':product['id'],'product_title':product['title'],
                                      'product_version':product['version'],'text':script['text'],
                                      'sha256':hashlib.sha256(script['text'].encode()).hexdigest()})
        reopened=ProductStore(root)
        if reopened.list()!=products or any(len(reopened.scripts(p['id']))!=1 for p in products):
            raise LLMError('数据库重开检查失败')
        if len({item['sha256'] for item in report['results']})!=2:
            raise LLMError('两商品返回相同话术，请检查串商品或无效生成')
        report.update(status='generated-awaiting-human-review',reopen_verified=True)
        return report,root,0
    except LLMError as error:
        report.update(status='not-passed',error=str(error))
        return report,root,2
    except Exception:
        report.update(status='not-passed',error='验收执行异常，请检查数据目录、权限及工作进程；原始异常未回显')
        return report,root,2
    finally:
        if manager: manager.close()
        (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


def main(argv=None):
    parser=argparse.ArgumentParser(description='V02-05真实LLM验收，结果需人工核对')
    parser.add_argument('--report-directory',type=Path,required=True)
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args(argv)
    report,root,code=run(args.report_directory,args.prepare_only)
    print(json.dumps({'status':report['status'],'report':str(root/'report.json'),
                      'human_review':report['human_review'],'error':report.get('error')},ensure_ascii=False))
    return code


if __name__=='__main__': raise SystemExit(main())
