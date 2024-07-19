import os
import pandas as pd
import time
import logging
import yaml
import sched
from string import Template

time_compress = 7

log_file_path = r'logs/test.log'
logging.basicConfig(filename=log_file_path, level=logging.DEBUG)
log = logging.getLogger(__name__)

csv_path = r'data/test.csv'
sorted_csv_path = r'data/sorted_test.csv'

cfg_template_path = r'templates/config_template.yml'
dpl_template_path = r'templates/deployment_template.yml'

config_path = r'configs/'
deployment_path = r'deployments/'


def is_replicas(row1, row2):
    return row1['jobId'] == row2['jobId'] \
           and row1['startTime'] == row2['startTime'] \
           and row1['endTime'] == row2['endTime']


def create_yml_files(test_index, config_file_name, replicas, cpu_count, memory_count):
    test_name = 'test-{}'.format(str(test_index))
    deployment_file_name = '{}deployment_finished.yml'.format(deployment_path)
    pod_name = 'test-finished'

    cpu = '{}m'.format(str(cpu_count * 1000))
    memory = '{}Mi'.format(str(1024 * memory_count))

    with open(cfg_template_path, encoding='utf-8') as fp:
        read_cfg = fp.read()
        config_template = Template(read_cfg)
        cfg_s = config_template.safe_substitute({'testName': test_name,
                                                 'objectTemplatePath': deployment_file_name,
                                                 'name': pod_name,
                                                 'replicas': replicas,
                                                 'cpu': cpu,
                                                 'memory': memory})
    cfg_yaml_data = yaml.safe_load(cfg_s)
    with open(config_file_name, 'w') as fp:
        yaml.dump(cfg_yaml_data, fp, sort_keys=False)


def exec_test(config_file_name, row_index):
    print('printing: {} row_index: {}'.format(config_file_name, row_index))


# execute cluster loader task
def exec_cluster_loader2(config_file_name):
    cluster_loader2_path = r'../clusterloader'
    cmd = '{} --testconfig={} --provider=kubemark --provider-configs=ROOT_KUBECONFIG=./config ' \
          '--kubeconfig=./config --v=2 --enable-exec-service=false --enable-prometheus-server=true ' \
          '--tear-down-prometheus-server=false  --report-dir="./reports" --nodes=10 2>&1 | tee output.txt'.format(
            cluster_loader2_path, config_file_name)
    os.system(cmd)


def run():
    try:
        df = pd.read_csv(csv_path)
        assert df.shape[0] >= 2
        df = df.sort_values('startTime', ascending=True)
        df.to_csv(sorted_csv_path, index=False)
    except Exception as e:
        log.error(e)
        print(e)
        raise

    test_index = 0
    row_index = 0
    replicas = 1
    global pre_row

    scheduler = sched.scheduler(time.time, time.sleep)
    csv_start_time = int(time.mktime(time.strptime(str(df['time'][0]), '%Y%m%d')))
    # 预留时间用于生成yml文件
    start_interval = 30
    # 实际任务开始执行时间
    exec_start_time = int(time.time()) + start_interval

    '''TODO: if row['state'] == 'running:
    '''

    for _, row in df.iterrows():
        time_interval = 0 if row['state'] == 'running' \
            else int((row['startTime'] - csv_start_time) / time_compress)
        if row_index > 0:
            if is_replicas(pre_row, row):
                replicas += 1
            else:
                config_file_name = '{}config-{}.yml'.format(config_path, str(test_index))
                create_yml_files(test_index, config_file_name, replicas, pre_row['cpuCount'], pre_row['memoryCount'])
                scheduler.enter(exec_start_time + time_interval - int(time.time()), 0,
                                exec_test, (config_file_name, row_index, ))
                replicas = 1
                test_index += 1
        row_index += 1
        pre_row = row
        if row_index == df.shape[0]:
            config_file_name = '{}config-{}.yml'.format(config_path, str(test_index))
            create_yml_files(test_index, config_file_name, replicas, pre_row['cpuCount'], pre_row['memoryCount'])
            scheduler.enter(exec_start_time + time_interval - int(time.time()), 0,
                            exec_test, (config_file_name, row_index, ))
            test_index += 1

    scheduler.run()


if __name__ == '__main__':
    run()
