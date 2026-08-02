def _task(name):
    def inner(*args, **kwargs): return {'task':name,'status':'queued','args':args,'kwargs':kwargs}
    return inner
execute_backtest=_task('execute_backtest'); run_optimization_job=_task('run_optimization_job'); run_monte_carlo=_task('run_monte_carlo'); run_walk_forward=_task('run_walk_forward'); prepare_replay=_task('prepare_replay'); generate_dataset=_task('generate_dataset'); calculate_statistics=_task('calculate_statistics'); run_benchmark_analysis=_task('run_benchmark_analysis')
