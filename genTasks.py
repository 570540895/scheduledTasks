import os
import time
import logging
import yaml
import sched
import sys
import pandas as pd
from string import Template

is_debug = True if sys.gettrace() else False

# 时间压缩比
time_compress = 7

# 构造负载倍数
load_times = 1
# 构造负载延迟(秒)
load_latency = 3

# 预留时间用于生成yml文件
start_interval = 30
# 任务启动延迟阈值
time_interval_threshold = 0

log_file = r'logs/test.log'
logging.basicConfig(filename=log_file, level=logging.DEBUG)
log = logging.getLogger(__name__)

csv_file = r'data/test.csv'
sorted_csv_file = r'data/sorted_test.csv'

cfg_template_path = r'templates/'

config_path = r'configs/'
deployment_path = r'deployments/'


def is_replicas(row1, row2):
    return row1['jobId'] == row2['jobId'] \
           and row1['startTime'] == row2['startTime'] \
           and row1['endTime'] == row2['endTime']


def create_yml_files(test_index, replicas, cpu_count, memory_count, is_running, timestamp_duration):
    config_file_name = '{}config-{}.yml'.format(config_path, str(test_index))
    test_name = 'test-{}'.format(str(test_index))
    pod_group_name = 'test-pod-{}'.format(str(test_index))
    deployment_group_name = 'test-deployment-{}'.format(str(test_index))
    deployment_file_name = '../{}{}'.format(deployment_path, 'deployment_finished.yml')
    pod_name = 'test-finished'

    cpu = '{}m'.format(str(cpu_count * 1000))
    memory = '{}Mi'.format(str(1024 * memory_count))
    duration = '{}m'.format(timestamp_duration)

    cfg_template_file = '{}{}'.format(cfg_template_path,
                                      'running_config_template.yml' if is_running else 'finished_config_template.yml')
    with open(cfg_template_file, encoding='utf-8') as fp:
        read_cfg = fp.read()
        config_template = Template(read_cfg)
        cfg_s = config_template.safe_substitute({'testName': test_name,
                                                 'podGroupName': pod_group_name,
                                                 'deploymentGroupName': deployment_group_name,
                                                 'objectTemplatePath': deployment_file_name,
                                                 'name': pod_name,
                                                 'replicas': replicas,
                                                 'cpu': cpu,
                                                 'memory': memory,
                                                 'duration': duration})
    cfg_yaml_data = yaml.safe_load(cfg_s)
    with open(config_file_name, 'w') as fp:
        yaml.dump(cfg_yaml_data, fp, sort_keys=False)


def exec_test(test_index, row_index, time_interval):
    config_file_name = 'config-{}.yml'.format(str(test_index))
    print('printing: {} row_index: {} time_interval: {}'.format(config_file_name, row_index, time_interval))


# execute cluster loader task
def exec_cluster_loader2(test_index):
    config_file_name = '{}config-{}.yml'.format(config_path, str(test_index))
    cluster_loader2_path = r'../clusterloader'
    kubemark_config_path = r'../config'
    enable_exec_service = r'false'
    enable_prometheus_server = r'false'
    tear_down_prometheus_server = r'false'
    report_dir = r'../reports'
    output_file_path = r'output.txt'
    cmd = '{} --testconfig={} --provider=kubemark --provider-configs=ROOT_KUBECONFIG={} ' \
          '--kubeconfig={} --v=2 --enable-exec-service={} --enable-prometheus-server={} ' \
          '--tear-down-prometheus-server={}  --report-dir="{}" --nodes=10 >{} 2>&1 &'.format(
            cluster_loader2_path, config_file_name, kubemark_config_path, kubemark_config_path,
            enable_exec_service, enable_prometheus_server, tear_down_prometheus_server, report_dir, output_file_path)
    os.system(cmd)


def run():
    try:
        df = pd.read_csv(csv_file)
        assert df.shape[0] >= 2
        df = df.sort_values('startTime', ascending=True)
        df.to_csv(sorted_csv_file, index=False)
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

    # 实际任务开始执行时间
    exec_start_time = int(time.time()) + start_interval

    for _, row in df.iterrows():
        if row_index == 0:
            row_index += 1
            pre_row = row
        else:
            if is_replicas(pre_row, row):
                replicas += 1
            else:
                time_interval = 0 if pre_row['startTime'] < csv_start_time \
                    else int((pre_row['startTime'] - csv_start_time) / time_compress)
                is_running = True if pre_row['state'] == 'running' else False
                duration = 0 if is_running else \
                    max(1, int((pre_row['endTime'] - max(pre_row['startTime'], csv_start_time)) / (60 * time_compress)))
                for i in range(load_times):
                    create_yml_files(test_index,  replicas, pre_row['cpuCount'],
                                     pre_row['memoryCount'], is_running, duration)
                    exec_func = exec_test if is_debug else exec_cluster_loader2
                    exec_func_params = (test_index, row_index, time_interval, ) if is_debug else (test_index, )
                    if time_interval >= time_interval_threshold:
                        scheduler.enter(exec_start_time + time_interval + i*load_latency - int(time.time()), 0,
                                        exec_func, exec_func_params)
                    test_index += 1
                replicas = 1
            row_index += 1
            pre_row = row
        if row_index == df.shape[0]:
            time_interval = 0 if pre_row['startTime'] < csv_start_time \
                else int((pre_row['startTime'] - csv_start_time) / time_compress)
            is_running = True if pre_row['state'] == 'running' else False
            duration = 0 if is_running else \
                max(1, int((pre_row['endTime'] - max(pre_row['startTime'], csv_start_time)) / (60 * time_compress)))
            for i in range(load_times):
                create_yml_files(test_index, replicas, pre_row['cpuCount'],
                                 pre_row['memoryCount'], is_running, duration)
                exec_func = exec_test if is_debug else exec_cluster_loader2
                exec_func_params = (test_index, row_index, time_interval,) if is_debug else (test_index,)
                if time_interval >= time_interval_threshold:
                    scheduler.enter(exec_start_time + time_interval + i*load_latency - int(time.time()), 0,
                                    exec_func, exec_func_params)
                test_index += 1
            replicas = 1

    scheduler.run()


if __name__ == '__main__':
    run()
